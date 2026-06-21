"""Rust-backed image asset wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Self, cast


class _RustCanvasImage(Protocol):
    width: int
    height: int
    version: int
    key: int

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int, int]: ...

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int, a: int) -> None: ...

    def replace_rgba_bytes(self, pixels: bytes) -> None: ...

    def copy(self) -> _RustCanvasImage: ...

    def crop(self, sx: int, sy: int, sw: int, sh: int) -> _RustCanvasImage: ...

    def resize(self, width: int, height: int) -> None: ...

    def mask(self, mask: _RustCanvasImage) -> None: ...

    def filter(self, mode: str, value: float | None) -> None: ...

    def alpha_composite(self, source: _RustCanvasImage, dx: int, dy: int) -> None: ...

    def save(self, path: str) -> None: ...

    def to_rgba_bytes(self) -> bytes: ...


class CanvasImage:
    """Rust-managed image asset."""

    def __init__(self, rust_image: _RustCanvasImage) -> None:
        self._rust_image = rust_image

    @classmethod
    def from_file(cls, path: str | Path) -> CanvasImage:
        from gummysnake.rust.canvas import require_canvas_runtime

        return cls(
            cast(_RustCanvasImage, require_canvas_runtime().CanvasImage.from_file(str(path)))
        )

    @classmethod
    def from_rgba_bytes(cls, width: int, height: int, pixels: bytes) -> CanvasImage:
        from gummysnake.rust.canvas import require_canvas_runtime

        return cls(
            cast(
                _RustCanvasImage,
                require_canvas_runtime().CanvasImage.from_rgba_bytes(width, height, pixels),
            )
        )

    @property
    def width(self) -> int:
        return int(self._rust_image.width)

    @property
    def height(self) -> int:
        return int(self._rust_image.height)

    @property
    def version(self) -> int:
        return int(self._rust_image.version)

    @property
    def cache_key(self) -> int:
        return int(self._rust_image.key)

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        r, g, b, a = self._rust_image.get_pixel(int(x), int(y))
        return int(r), int(g), int(b), int(a)

    def set_pixel(self, x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        r, g, b, a = rgba
        self._rust_image.set_pixel(int(x), int(y), int(r), int(g), int(b), int(a))

    def replace_rgba_bytes(self, pixels: bytes) -> None:
        self._rust_image.replace_rgba_bytes(pixels)

    def copy(self) -> Self:
        return type(self)(self._rust_image.copy())

    def crop(self, sx: int, sy: int, sw: int, sh: int) -> Self:
        return type(self)(self._rust_image.crop(int(sx), int(sy), int(sw), int(sh)))

    def resize(self, width: int, height: int) -> None:
        self._rust_image.resize(int(width), int(height))

    def mask(self, mask: CanvasImage) -> None:
        self._rust_image.mask(mask._rust_image)

    def filter(self, mode: str, value: float | None) -> None:
        self._rust_image.filter(mode, value)

    def alpha_composite(self, source: CanvasImage, dx: int, dy: int) -> None:
        self._rust_image.alpha_composite(source._rust_image, int(dx), int(dy))

    def to_rgba_bytes(self) -> bytes:
        return bytes(self._rust_image.to_rgba_bytes())

    def save(self, path: str | Path) -> None:
        self._rust_image.save(str(path))


__all__ = ["CanvasImage"]
