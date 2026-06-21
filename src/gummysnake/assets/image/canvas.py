"""Rust-backed image asset wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class _RustCanvasImage(Protocol):
    width: int
    height: int
    version: int

    def save(self, path: str) -> None: ...

    def to_rgba_bytes(self) -> bytes: ...


class CanvasImage:
    """Rust-managed image asset."""

    def __init__(self, rust_image: _RustCanvasImage) -> None:
        self._rust_image = rust_image

    @classmethod
    def from_file(cls, path: str | Path) -> CanvasImage:
        from gummysnake.rust.canvas import require_canvas_extension

        return cls(require_canvas_extension().CanvasImage.from_file(str(path)))

    @classmethod
    def from_rgba_bytes(cls, width: int, height: int, pixels: bytes) -> CanvasImage:
        from gummysnake.rust.canvas import require_canvas_extension

        return cls(require_canvas_extension().CanvasImage.from_rgba_bytes(width, height, pixels))

    @property
    def width(self) -> int:
        return int(self._rust_image.width)

    @property
    def height(self) -> int:
        return int(self._rust_image.height)

    @property
    def version(self) -> int:
        return int(self._rust_image.version)

    def to_rgba_bytes(self) -> bytes:
        return bytes(self._rust_image.to_rgba_bytes())

    def save(self, path: str | Path) -> None:
        self._rust_image.save(str(path))


__all__ = ["CanvasImage"]
