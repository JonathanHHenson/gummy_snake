"""Rust-managed sound asset wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


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


__all__ = ["CanvasSound"]
