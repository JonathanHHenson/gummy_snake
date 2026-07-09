"""Backend-neutral sound loading and playback helpers."""

from __future__ import annotations

import atexit
import shutil
import signal
import subprocess
import tempfile
import threading
import weakref
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol, cast

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError

_ACTIVE_NATIVE_PLAYERS: weakref.WeakSet[_NativeAudioPlayer] = weakref.WeakSet()
_ACTIVE_NATIVE_PLAYERS_LOCK = threading.Lock()
_NATIVE_PLAYER_MONITOR_STARTED = False


class _ByteSourceCallback(Protocol):
    def __call__(self) -> bytes | bytearray | memoryview: ...


class _RustCanvasSound(Protocol):
    path: str
    duration: float | None
    byte_len: int

    @staticmethod
    def from_file(path: str) -> _RustCanvasSound: ...

    def to_bytes(self) -> bytes: ...


class CanvasSound:
    """Rust-managed sound asset bytes and metadata."""

    def __init__(self, rust_sound: _RustCanvasSound) -> None:
        """Wrap a Rust-managed sound asset handle."""
        self._rust_sound = rust_sound

    @classmethod
    def from_file(cls, path: str | Path) -> CanvasSound:
        """Load sound bytes and metadata through the Rust canvas runtime.

        Args:
            path: Sound file to read.

        Returns:
            A Rust-managed sound asset handle.
        """

        from gummysnake.rust.canvas import require_canvas_runtime

        return cls(require_canvas_runtime().CanvasSound.from_file(str(path)))

    @property
    def path(self) -> Path:
        """Path to the loaded sound file."""

        return Path(self._rust_sound.path)

    @property
    def duration(self) -> float | None:
        """Sound duration in seconds, if the runtime could read it."""

        duration = self._rust_sound.duration
        return None if duration is None else float(duration)

    @property
    def byte_len(self) -> int:
        """Number of encoded audio bytes stored by the runtime."""

        return int(self._rust_sound.byte_len)

    def to_bytes(self) -> bytes:
        """Return the encoded audio bytes.

        Returns:
            The original sound file bytes owned by the Rust runtime.
        """

        return self._rust_sound.to_bytes()


class Sound:
    """Loaded sound asset with simple playback controls.

    Loading is backend-neutral and does not require an audio device. Playback is
    delegated to a small platform player when one is available; otherwise
    ``play()`` raises ``BackendCapabilityError`` while metadata and controls
    remain usable for sketches and tests.
    """

    def __init__(
        self,
        source: object,
        *,
        path: Path,
        rust_sound: CanvasSound | None = None,
        player_factory: Any | None = None,
    ) -> None:
        """Create a playable sound wrapper around asset bytes or a generated source."""
        self._source = source
        self._rust_sound = rust_sound
        self._path = path
        self._player_factory = player_factory or _NativeAudioPlayer
        self._player: Any | None = None
        self._temporary_playback_path: Path | None = None
        self._volume = 1.0
        self._rate = 1.0
        self._pan = 0.0
        self._loop = False
        self._position = 0.0
        self._is_playing = False
        self._ended_callbacks: list[Callable[[Sound], object]] = []

    @property
    def path(self) -> Path:
        """Path used to create this sound."""

        return self._path

    @property
    def duration(self) -> float | None:
        """Sound duration in seconds, if known."""

        if self._rust_sound is not None:
            return self._rust_sound.duration
        duration = getattr(self._source, "duration", None)
        return None if duration is None else float(duration)

    @property
    def byte_len(self) -> int | None:
        """Number of encoded audio bytes, if bytes are available."""

        if self._rust_sound is None:
            return None
        return self._rust_sound.byte_len

    def to_bytes(self) -> bytes:
        """Return the encoded sound bytes.

        Returns:
            Audio file bytes for this sound.
        """

        if self._rust_sound is not None:
            return self._rust_sound.to_bytes()
        to_bytes = getattr(self._source, "to_bytes", None)
        if callable(to_bytes):
            return bytes(cast(_ByteSourceCallback, to_bytes)())
        raise BackendCapabilityError("Sound bytes are unavailable for this sound source.")

    def play(self) -> None:
        """Start playback from the current sound source."""

        self.stop()
        player = self._create_player()
        self._queue_source(player)
        self._apply_controls(player)
        try:
            player.play()
        except BackendCapabilityError:
            self._dispose_player(player)
            raise
        except Exception as exc:  # pragma: no cover - backend-specific failure path
            self._dispose_player(player)
            raise BackendCapabilityError(
                f"Audio playback is unavailable on this system. Could not play {self._path!s}."
            ) from exc
        self._player = player
        self._is_playing = True

    def loop(self) -> None:
        """Enable looping and start playback."""

        self.looping(True)
        self.play()

    def no_loop(self) -> None:
        """Disable looping for future playback."""

        self.looping(False)

    def looping(self, value: bool | None = None) -> bool:
        """Get or set whether the sound repeats when it reaches the end.

        Args:
            value: Optional new looping flag.

        Returns:
            The current looping flag.
        """

        if value is not None:
            self._loop = bool(value)
            if self._player is not None and hasattr(self._player, "loop"):
                self._player.loop = self._loop
        return self._loop

    def pause(self) -> None:
        """Pause playback if a player is active."""

        if self._player is None:
            return
        pause = getattr(self._player, "pause", None)
        if callable(pause):
            pause()
        self._is_playing = False

    def stop(self) -> None:
        """Stop playback, seek back to the start, and release the player."""

        player = self._player
        if player is None:
            return
        pause = getattr(player, "pause", None)
        if callable(pause):
            pause()
        seek = getattr(player, "seek", None)
        if callable(seek):
            seek(0.0)
        self._position = 0.0
        self._is_playing = False
        self._dispose_player(player)
        self._player = None

    def close(self) -> None:
        """Stop playback and release any temporary playback resources."""

        self.stop()

    def volume(self, value: float | None = None) -> float:
        """Get or set playback volume.

        Args:
            value: Optional non-negative volume value, where ``1.0`` is normal volume.

        Returns:
            The current volume value.
        """

        if value is not None:
            if value < 0:
                raise ArgumentValidationError("Sound.volume() cannot be negative.")
            self._volume = float(value)
            if self._player is not None:
                self._player.volume = self._volume
        return self._volume

    def rate(self, value: float | None = None) -> float:
        """Get or set playback speed.

        Args:
            value: Optional positive speed multiplier, where ``1.0`` is normal speed.

        Returns:
            The current speed multiplier.
        """

        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("Sound.rate() must be positive.")
            self._rate = float(value)
            if self._player is not None:
                self._player.pitch = self._rate
        return self._rate

    def pan(self, value: float | None = None) -> float:
        """Get or set stereo pan.

        Args:
            value: Optional pan value from ``-1.0`` for left to ``1.0`` for right.

        Returns:
            The current pan value.
        """

        if value is not None:
            if not -1.0 <= value <= 1.0:
                raise ArgumentValidationError("Sound.pan() must be between -1 and 1.")
            self._pan = float(value)
            if self._player is not None:
                self._player.position = (self._pan, 0.0, 0.0)
        return self._pan

    def seek(self, seconds: float) -> None:
        """Move playback to a time in the sound.

        Args:
            seconds: Non-negative time position in seconds.
        """

        if seconds < 0:
            raise ArgumentValidationError("Sound.seek() cannot be negative.")
        self._position = float(seconds)
        if self._player is not None:
            seek = getattr(self._player, "seek", None)
            if callable(seek):
                seek(self._position)

    def time(self) -> float:
        """Return the current playback position in seconds."""

        if self._player is not None:
            time = getattr(self._player, "time", None)
            if callable(time):
                return float(cast(Any, time)())
            get_time = getattr(self._player, "get_time", None)
            if callable(get_time):
                return float(cast(Any, get_time)())
        return self._position

    def is_playing(self) -> bool:
        """Return whether this sound is currently playing."""

        return self._is_playing

    def is_paused(self) -> bool:
        """Return whether this sound has an active player that is paused."""

        return self._player is not None and not self._is_playing

    def on_ended(self, callback: Callable[[Sound], object]) -> Callable[[Sound], object]:
        """Register a callback to run when playback ends.

        Args:
            callback: Function that accepts this ``Sound`` instance.

        Returns:
            The same callback, so the method can be used like a decorator.
        """

        if not callable(callback):
            raise ArgumentValidationError("Sound.on_ended() requires a callable.")
        self._ended_callbacks.append(callback)
        return callback

    def _notify_ended(self) -> None:
        self._is_playing = False
        for callback in tuple(self._ended_callbacks):
            callback(self)

    def _create_player(self) -> Any:
        playback_path = self._materialize_playback_path()
        try:
            return self._player_factory(playback_path)
        except Exception as exc:  # pragma: no cover - backend-specific failure path
            self._remove_temporary_playback_file()
            raise BackendCapabilityError(
                "Audio playback is unavailable on this system. Could not create a sound player."
            ) from exc

    def _materialize_playback_path(self) -> Path:
        if self._rust_sound is not None:
            return self._path
        to_bytes = getattr(self._source, "to_bytes", None)
        if not callable(to_bytes):
            return self._path
        suffix = self._path.suffix or ".wav"
        with tempfile.NamedTemporaryFile(
            prefix="gummysnake-sound-", suffix=suffix, delete=False
        ) as file:
            file.write(bytes(cast(_ByteSourceCallback, to_bytes)()))
            temporary_path = Path(file.name)
        self._temporary_playback_path = temporary_path
        return temporary_path

    def _queue_source(self, player: Any) -> None:
        queue = getattr(player, "queue", None)
        if callable(queue):
            queue(self._source)

    def _apply_controls(self, player: Any) -> None:
        if hasattr(player, "volume"):
            player.volume = self._volume
        if hasattr(player, "pitch"):
            player.pitch = self._rate
        if hasattr(player, "position"):
            player.position = (self._pan, 0.0, 0.0)
        if hasattr(player, "loop"):
            player.loop = self._loop

    def _dispose_player(self, player: Any) -> None:
        delete = getattr(player, "delete", None)
        if callable(delete):
            delete()
        self._remove_temporary_playback_file()

    def _remove_temporary_playback_file(self) -> None:
        temporary_path = self._temporary_playback_path
        self._temporary_playback_path = None
        if temporary_path is None:
            return
        with suppress(OSError):
            temporary_path.unlink(missing_ok=True)


def load_sound(path: str | Path) -> Sound:
    """Load a sound file for playback and byte access.

    Args:
        path: File path or package-relative asset path to an existing sound.

    Returns:
        A Sound object with playback controls and metadata.
    """
    sound_path = resolve_asset_path(path)
    if not sound_path.exists():
        raise ArgumentValidationError(f"Sound file does not exist: {sound_path!s}.")
    try:
        rust_sound = CanvasSound.from_file(sound_path)
    except BackendCapabilityError:
        raise
    except Exception as exc:
        raise ArgumentValidationError(f"Could not load sound {sound_path!s}.") from exc
    return Sound(rust_sound, path=sound_path, rust_sound=rust_sound)


async def load_sound_async(path: str | Path) -> Sound:
    """Load a sound file using the async asset-loading API.

    Args:
        path: File path or package-relative asset path to an existing sound.

    Returns:
        A Sound object with playback controls and metadata.
    """
    return load_sound(path)


class _NativeAudioPlayer:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._process: subprocess.Popen[bytes] | None = None
        self.volume = 1.0
        self.pitch = 1.0
        self.position = (0.0, 0.0, 0.0)

    def play(self) -> None:
        command = _platform_play_command(self._path)
        if command is None:
            raise BackendCapabilityError(
                "Audio playback requires an available platform player such as afplay, paplay, "
                "aplay, or ffplay."
            )
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _register_native_audio_player(self)

    def pause(self) -> None:
        if self._process is None:
            return
        if hasattr(signal, "SIGSTOP"):
            self._process.send_signal(signal.SIGSTOP)
        else:  # pragma: no cover - Windows-specific fallback
            self.delete()

    def seek(self, value: float) -> None:
        if value == 0:
            self.delete()

    def delete(self) -> None:
        process = self._process
        self._process = None
        _unregister_native_audio_player(self)
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:  # pragma: no cover - process-specific failure path
            process.kill()
            with suppress(Exception):
                process.wait(timeout=1.0)


def _register_native_audio_player(player: _NativeAudioPlayer) -> None:
    global _NATIVE_PLAYER_MONITOR_STARTED
    should_start_monitor = False
    with _ACTIVE_NATIVE_PLAYERS_LOCK:
        _ACTIVE_NATIVE_PLAYERS.add(player)
        if not _NATIVE_PLAYER_MONITOR_STARTED:
            _NATIVE_PLAYER_MONITOR_STARTED = True
            should_start_monitor = True
    if should_start_monitor:
        threading.Thread(
            target=_stop_native_audio_when_main_thread_exits,
            name="gummysnake-audio-cleanup",
            daemon=True,
        ).start()


def _unregister_native_audio_player(player: _NativeAudioPlayer) -> None:
    with _ACTIVE_NATIVE_PLAYERS_LOCK:
        _ACTIVE_NATIVE_PLAYERS.discard(player)


def _stop_native_audio_when_main_thread_exits() -> None:
    main_thread = threading.main_thread()
    if threading.current_thread() is main_thread:  # pragma: no cover - defensive guard
        return
    with suppress(RuntimeError):
        main_thread.join()
    _stop_active_native_audio_players()


def _stop_active_native_audio_players() -> None:
    with _ACTIVE_NATIVE_PLAYERS_LOCK:
        players = list(_ACTIVE_NATIVE_PLAYERS)
    for player in players:
        with suppress(Exception):
            player.delete()


atexit.register(_stop_active_native_audio_players)


def _platform_play_command(path: Path) -> list[str] | None:
    if player := shutil.which("afplay"):
        return [player, str(path)]
    if player := shutil.which("paplay"):
        return [player, str(path)]
    if player := shutil.which("aplay"):
        return [player, str(path)]
    if player := shutil.which("ffplay"):
        return [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
    return None


__all__ = ["CanvasSound", "Sound", "load_sound", "load_sound_async"]
