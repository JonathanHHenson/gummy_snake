"""Backend-neutral sound loading and playback helpers."""

from __future__ import annotations

import shutil
import signal
import subprocess
import tempfile
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol, cast

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


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
        """From file for this CanvasSound.
        
        Args:
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            The return value. Type: `CanvasSound`.
        """
        from gummysnake.rust.canvas import require_canvas_runtime

        return cls(require_canvas_runtime().CanvasSound.from_file(str(path)))

    @property
    def path(self) -> Path:
        """Return the asset path.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Path`.
        """
        return Path(self._rust_sound.path)

    @property
    def duration(self) -> float | None:
        """Return this CanvasSound's duration.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float | None`.
        """
        duration = self._rust_sound.duration
        return None if duration is None else float(duration)

    @property
    def byte_len(self) -> int:
        """Return this CanvasSound's byte len.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return int(self._rust_sound.byte_len)

    def to_bytes(self) -> bytes:
        """Return this CanvasSound converted to bytes.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bytes`.
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
        """Return the asset path.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Path`.
        """
        return self._path

    @property
    def duration(self) -> float | None:
        """Return this Sound's duration.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float | None`.
        """
        if self._rust_sound is not None:
            return self._rust_sound.duration
        duration = getattr(self._source, "duration", None)
        return None if duration is None else float(duration)

    @property
    def byte_len(self) -> int | None:
        """Return this Sound's byte len.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int | None`.
        """
        if self._rust_sound is None:
            return None
        return self._rust_sound.byte_len

    def to_bytes(self) -> bytes:
        """Return this Sound converted to bytes.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bytes`.
        """
        if self._rust_sound is not None:
            return self._rust_sound.to_bytes()
        to_bytes = getattr(self._source, "to_bytes", None)
        if callable(to_bytes):
            return bytes(cast(_ByteSourceCallback, to_bytes)())
        raise BackendCapabilityError("Sound bytes are unavailable for this sound source.")

    def play(self) -> None:
        """Start playback for this object.
        
        Args:
            None.
        
        Returns:
            None.
        """
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
        """Loop this Sound.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self.looping(True)
        self.play()

    def no_loop(self) -> None:
        """Disable loop for subsequent operations.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self.looping(False)

    def looping(self, value: bool | None = None) -> bool:
        """Looping for this Sound.
        
        Args:
            value: The value value. Expected type: `bool | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `bool`.
        """
        if value is not None:
            self._loop = bool(value)
            if self._player is not None and hasattr(self._player, "loop"):
                self._player.loop = self._loop
        return self._loop

    def pause(self) -> None:
        """Pause playback for this object.
        
        Args:
            None.
        
        Returns:
            None.
        """
        if self._player is None:
            return
        pause = getattr(self._player, "pause", None)
        if callable(pause):
            pause()
        self._is_playing = False

    def stop(self) -> None:
        """Stop this Sound.
        
        Args:
            None.
        
        Returns:
            None.
        """
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
        """Close this Sound.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self.stop()

    def volume(self, value: float | None = None) -> float:
        """Volume for this Sound.
        
        Args:
            value: The value value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        if value is not None:
            if value < 0:
                raise ArgumentValidationError("Sound.volume() cannot be negative.")
            self._volume = float(value)
            if self._player is not None:
                self._player.volume = self._volume
        return self._volume

    def rate(self, value: float | None = None) -> float:
        """Rate for this Sound.
        
        Args:
            value: The value value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("Sound.rate() must be positive.")
            self._rate = float(value)
            if self._player is not None:
                self._player.pitch = self._rate
        return self._rate

    def pan(self, value: float | None = None) -> float:
        """Return or set stereo pan for this sound.
        
        Args:
            value: The value value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        if value is not None:
            if not -1.0 <= value <= 1.0:
                raise ArgumentValidationError("Sound.pan() must be between -1 and 1.")
            self._pan = float(value)
            if self._player is not None:
                self._player.position = (self._pan, 0.0, 0.0)
        return self._pan

    def seek(self, seconds: float) -> None:
        """Seek for this Sound.
        
        Args:
            seconds: The seconds value. Expected type: `float`.
        
        Returns:
            None.
        """
        if seconds < 0:
            raise ArgumentValidationError("Sound.seek() cannot be negative.")
        self._position = float(seconds)
        if self._player is not None:
            seek = getattr(self._player, "seek", None)
            if callable(seek):
                seek(self._position)

    def time(self) -> float:
        """Time for this Sound.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        if self._player is not None:
            time = getattr(self._player, "time", None)
            if callable(time):
                return float(cast(Any, time)())
            get_time = getattr(self._player, "get_time", None)
            if callable(get_time):
                return float(cast(Any, get_time)())
        return self._position

    def is_playing(self) -> bool:
        """Return whether playing is active.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._is_playing

    def is_paused(self) -> bool:
        """Return whether paused is active.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._player is not None and not self._is_playing

    def on_ended(self, callback: Callable[[Sound], object]) -> Callable[[Sound], object]:
        """On ended for this Sound.
        
        Args:
            callback: The callback value. Expected type: `Callable[[Sound], object]`.
        
        Returns:
            The return value. Type: `Callable[[Sound], object]`.
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
    """Load and return sound.
    
    Args:
        path: The path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Sound`.
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
    """Load and return a sound asynchronously.
    
    Args:
        path: The path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Sound`.
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
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:  # pragma: no cover - process-specific failure path
            process.kill()


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
