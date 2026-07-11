"""Native platform-player and temporary-resource support for :mod:`gummysnake.assets.sound`.

This private module owns subprocess lifecycle concerns.  The public ``Sound``
asset remains a small Python wrapper around a Rust-owned ``CanvasSound`` handle.
"""

from __future__ import annotations

import atexit
import shutil
import signal
import subprocess
import tempfile
import threading
import weakref
from contextlib import suppress
from pathlib import Path
from typing import Protocol, cast

from gummysnake.exceptions import BackendCapabilityError


class _ByteSourceCallback(Protocol):
    def __call__(self) -> bytes | bytearray | memoryview: ...


class PlaybackResource:
    """A playback path and any temporary file needed to provide it."""

    def __init__(self, path: Path, source: object, *, rust_backed: bool) -> None:
        self._temporary_path: Path | None = None
        self.path = path if rust_backed else self._materialize_path(path, source)

    def close(self) -> None:
        """Release the temporary playback file, if this resource created one."""

        temporary_path = self._temporary_path
        self._temporary_path = None
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)

    def _materialize_path(self, path: Path, source: object) -> Path:
        to_bytes = getattr(source, "to_bytes", None)
        if not callable(to_bytes):
            return path
        suffix = path.suffix or ".wav"
        with tempfile.NamedTemporaryFile(
            prefix="gummysnake-sound-", suffix=suffix, delete=False
        ) as file:
            file.write(bytes(cast(_ByteSourceCallback, to_bytes)()))
            temporary_path = Path(file.name)
        self._temporary_path = temporary_path
        return temporary_path


class NativeAudioPlayer:
    """A small subprocess adapter for a supported platform audio player."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._process: subprocess.Popen[bytes] | None = None
        self.volume = 1.0
        self.pitch = 1.0
        self.position = (0.0, 0.0, 0.0)

    def play(self) -> None:
        command = self._play_command()
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
        else:  # pragma: no cover - Windows-specific behavior
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

    def _play_command(self) -> list[str] | None:
        return platform_play_command(self._path)


_ACTIVE_NATIVE_PLAYERS: weakref.WeakSet[NativeAudioPlayer] = weakref.WeakSet()
_ACTIVE_NATIVE_PLAYERS_LOCK = threading.Lock()
_NATIVE_PLAYER_MONITOR_STARTED = False


def _register_native_audio_player(player: NativeAudioPlayer) -> None:
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


def _unregister_native_audio_player(player: NativeAudioPlayer) -> None:
    with _ACTIVE_NATIVE_PLAYERS_LOCK:
        _ACTIVE_NATIVE_PLAYERS.discard(player)


def _stop_native_audio_when_main_thread_exits() -> None:
    main_thread = threading.main_thread()
    if threading.current_thread() is main_thread:  # pragma: no cover - defensive guard
        return
    with suppress(RuntimeError):
        main_thread.join()
    stop_active_native_audio_players()


def stop_active_native_audio_players() -> None:
    """Stop every live native player during explicit or interpreter shutdown."""

    with _ACTIVE_NATIVE_PLAYERS_LOCK:
        players = list(_ACTIVE_NATIVE_PLAYERS)
    for player in players:
        with suppress(Exception):
            player.delete()


def platform_play_command(path: Path) -> list[str] | None:
    """Return the first supported platform-player command, if any."""

    if player := shutil.which("afplay"):
        return [player, str(path)]
    if player := shutil.which("paplay"):
        return [player, str(path)]
    if player := shutil.which("aplay"):
        return [player, str(path)]
    if player := shutil.which("ffplay"):
        return [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
    return None


atexit.register(stop_active_native_audio_players)


__all__ = [
    "NativeAudioPlayer",
    "PlaybackResource",
    "platform_play_command",
    "stop_active_native_audio_players",
]
