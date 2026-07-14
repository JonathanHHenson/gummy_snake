"""Rust-managed sound asset wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class _RustCanvasPlayback(Protocol):
    duration: float
    error: str | None

    def play(self) -> None: ...

    def pause(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...

    def looping(self, value: bool | None = None) -> bool: ...

    def set_volume(self, value: float) -> None: ...

    def set_rate(self, value: float) -> None: ...

    def set_pan(self, value: float) -> None: ...

    def seek(self, seconds: float) -> None: ...

    def time(self) -> float: ...

    def is_playing(self) -> bool: ...

    def is_paused(self) -> bool: ...

    def take_ended(self) -> bool: ...

    def diagnostics(self) -> dict[str, object]: ...


class _RustCanvasSound(Protocol):
    path: str
    duration: float
    byte_len: int
    sample_rate: int
    frame_count: int

    @staticmethod
    def from_file(path: str) -> _RustCanvasSound: ...

    @staticmethod
    def from_bytes(path: str, payload: bytes) -> _RustCanvasSound: ...

    def to_bytes(self) -> bytes: ...

    def play(
        self,
        volume: float = 1.0,
        rate: float = 1.0,
        pan: float = 0.0,
        looping: bool = False,
        position: float = 0.0,
    ) -> _RustCanvasPlayback: ...


class CanvasSound:
    """Rust-managed sound asset bytes and metadata."""

    def __init__(self, rust_sound: _RustCanvasSound) -> None:
        """Wrap a Rust-managed sound asset handle."""
        self._rust_sound = rust_sound

    @classmethod
    def from_rust(cls, rust_sound: _RustCanvasSound) -> CanvasSound:
        """Wrap an existing Rust-owned rendered audio asset without copying bytes."""

        return cls(rust_sound)

    @classmethod
    def from_bytes(cls, path: str | Path, payload: bytes) -> CanvasSound:
        """Create a Rust-owned audio asset from encoded PCM WAV bytes."""

        from gummysnake.rust.canvas import require_canvas_runtime

        return cls(require_canvas_runtime().CanvasSound.from_bytes(str(path), payload))

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
    def duration(self) -> float:
        """Sound duration in seconds."""

        return float(self._rust_sound.duration)

    @property
    def byte_len(self) -> int:
        """Number of encoded audio bytes stored by the runtime."""

        return int(self._rust_sound.byte_len)

    @property
    def sample_rate(self) -> int:
        """Native sample rate of the decoded asset."""

        return int(self._rust_sound.sample_rate)

    @property
    def frame_count(self) -> int:
        """Number of decoded source frames."""

        return int(self._rust_sound.frame_count)

    def play(
        self,
        *,
        volume: float = 1.0,
        rate: float = 1.0,
        pan: float = 0.0,
        looping: bool = False,
        position: float = 0.0,
    ) -> _RustCanvasPlayback:
        """Start an independent voice on the shared native SDL mixer."""

        return self._rust_sound.play(volume, rate, pan, looping, position)

    def to_bytes(self) -> bytes:
        """Return the encoded audio bytes.

        Returns:
            The original sound file bytes owned by the Rust runtime.
        """

        return self._rust_sound.to_bytes()


__all__ = ["CanvasSound"]
