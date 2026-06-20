"""Backend-neutral sound loading and playback helpers."""

from __future__ import annotations

import shutil
import signal
import subprocess
import wave
from pathlib import Path
from typing import Any

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


class Sound:
    """Loaded sound asset with simple playback controls.

    Loading is backend-neutral and does not require an audio device. Playback is
    delegated to a small platform player when one is available; otherwise
    ``play()`` raises ``BackendCapabilityError`` while metadata and controls
    remain usable for sketches and tests.
    """

    def __init__(self, source: object, *, path: Path, player_factory: Any | None = None) -> None:
        self._source = source
        self._path = path
        self._player_factory = player_factory or _NativeAudioPlayer
        self._player: Any | None = None
        self._volume = 1.0
        self._rate = 1.0
        self._pan = 0.0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def duration(self) -> float | None:
        duration = getattr(self._source, "duration", None)
        return None if duration is None else float(duration)

    def play(self) -> None:
        self.stop()
        player = self._create_player()
        self._queue_source(player)
        self._apply_controls(player)
        try:
            player.play()
        except Exception as exc:  # pragma: no cover - backend-specific failure path
            self._dispose_player(player)
            raise BackendCapabilityError(
                f"Audio playback is unavailable on this system. Could not play {self._path!s}."
            ) from exc
        self._player = player

    def pause(self) -> None:
        if self._player is None:
            return
        pause = getattr(self._player, "pause", None)
        if callable(pause):
            pause()

    def stop(self) -> None:
        player = self._player
        if player is None:
            return
        pause = getattr(player, "pause", None)
        if callable(pause):
            pause()
        seek = getattr(player, "seek", None)
        if callable(seek):
            seek(0.0)
        self._dispose_player(player)
        self._player = None

    def volume(self, value: float | None = None) -> float:
        if value is not None:
            if value < 0:
                raise ArgumentValidationError("Sound.volume() cannot be negative.")
            self._volume = float(value)
            if self._player is not None:
                self._player.volume = self._volume
        return self._volume

    def rate(self, value: float | None = None) -> float:
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("Sound.rate() must be positive.")
            self._rate = float(value)
            if self._player is not None:
                self._player.pitch = self._rate
        return self._rate

    def pan(self, value: float | None = None) -> float:
        if value is not None:
            if not -1.0 <= value <= 1.0:
                raise ArgumentValidationError("Sound.pan() must be between -1 and 1.")
            self._pan = float(value)
            if self._player is not None:
                self._player.position = (self._pan, 0.0, 0.0)
        return self._pan

    def _create_player(self) -> Any:
        try:
            return self._player_factory(self._path)
        except Exception as exc:  # pragma: no cover - backend-specific failure path
            raise BackendCapabilityError(
                "Audio playback is unavailable on this system. Could not create a sound player."
            ) from exc

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

    def _dispose_player(self, player: Any) -> None:
        delete = getattr(player, "delete", None)
        if callable(delete):
            delete()


def load_sound(path: str | Path) -> Sound:
    sound_path = resolve_asset_path(path)
    if not sound_path.exists():
        raise ArgumentValidationError(f"Sound file does not exist: {sound_path!s}.")
    source = _load_audio_source(sound_path)
    return Sound(source, path=sound_path)


async def load_sound_async(path: str | Path) -> Sound:
    return load_sound(path)


class _AudioSource:
    def __init__(self, *, duration: float | None) -> None:
        self.duration = duration


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


def _load_audio_source(path: Path) -> _AudioSource:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                duration = frames / rate if rate > 0 else None
                return _AudioSource(duration=duration)
        except wave.Error as exc:
            raise ArgumentValidationError(f"Could not load sound {path!s}.") from exc
    return _AudioSource(duration=None)


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


__all__ = ["Sound", "load_sound", "load_sound_async"]
