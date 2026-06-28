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
        """Wrap a Rust-managed canvas image handle."""
        self._rust_image = rust_image

    @classmethod
    def from_file(cls, path: str | Path) -> CanvasImage:
        """From file for this CanvasImage.
        
        Args:
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            The return value. Type: `CanvasImage`.
        """
        from gummysnake.rust.canvas import require_canvas_runtime

        return cls(
            cast(_RustCanvasImage, require_canvas_runtime().CanvasImage.from_file(str(path)))
        )

    @classmethod
    def from_rgba_bytes(cls, width: int, height: int, pixels: bytes) -> CanvasImage:
        """From rgba bytes for this CanvasImage.
        
        Args:
            width: The width value. Expected type: `int`.
            height: The height value. Expected type: `int`.
            pixels: The pixels value. Expected type: `bytes`.
        
        Returns:
            The return value. Type: `CanvasImage`.
        """
        from gummysnake.rust.canvas import require_canvas_runtime

        return cls(
            cast(
                _RustCanvasImage,
                require_canvas_runtime().CanvasImage.from_rgba_bytes(width, height, pixels),
            )
        )

    @property
    def width(self) -> int:
        """Return this CanvasImage's width.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return int(self._rust_image.width)

    @property
    def height(self) -> int:
        """Return this CanvasImage's height.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return int(self._rust_image.height)

    @property
    def version(self) -> int:
        """Version for this CanvasImage.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return int(self._rust_image.version)

    @property
    def cache_key(self) -> int:
        """Cache key for this CanvasImage.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return int(self._rust_image.key)

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        """Return the current pixel value.
        
        Args:
            x: The x value. Expected type: `int`.
            y: The y value. Expected type: `int`.
        
        Returns:
            The return value. Type: `tuple[int, int, int, int]`.
        """
        r, g, b, a = self._rust_image.get_pixel(int(x), int(y))
        return int(r), int(g), int(b), int(a)

    def set_pixel(self, x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        """Set the pixel value.
        
        Args:
            x: The x value. Expected type: `int`.
            y: The y value. Expected type: `int`.
            rgba: The rgba value. Expected type: `tuple[int, int, int, int]`.
        
        Returns:
            None.
        """
        r, g, b, a = rgba
        self._rust_image.set_pixel(int(x), int(y), int(r), int(g), int(b), int(a))

    def replace_rgba_bytes(self, pixels: bytes) -> None:
        """Replace rgba bytes for this CanvasImage.
        
        Args:
            pixels: The pixels value. Expected type: `bytes`.
        
        Returns:
            None.
        """
        self._rust_image.replace_rgba_bytes(pixels)

    def copy(self) -> Self:
        """Copy for this CanvasImage.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Self`.
        """
        return type(self)(self._rust_image.copy())

    def crop(self, sx: int, sy: int, sw: int, sh: int) -> Self:
        """Crop for this CanvasImage.
        
        Args:
            sx: The sx value. Expected type: `int`.
            sy: The sy value. Expected type: `int`.
            sw: The sw value. Expected type: `int`.
            sh: The sh value. Expected type: `int`.
        
        Returns:
            The return value. Type: `Self`.
        """
        return type(self)(self._rust_image.crop(int(sx), int(sy), int(sw), int(sh)))

    def resize(self, width: int, height: int) -> None:
        """Resize for this CanvasImage.
        
        Args:
            width: The width value. Expected type: `int`.
            height: The height value. Expected type: `int`.
        
        Returns:
            None.
        """
        self._rust_image.resize(int(width), int(height))

    def mask(self, mask: CanvasImage) -> None:
        """Mask for this CanvasImage.
        
        Args:
            mask: The mask value. Expected type: `CanvasImage`.
        
        Returns:
            None.
        """
        self._rust_image.mask(mask._rust_image)

    def filter(self, mode: str, value: float | None) -> None:
        """Filter for this CanvasImage.
        
        Args:
            mode: The mode value. Expected type: `str`.
            value: The value value. Expected type: `float | None`.
        
        Returns:
            None.
        """
        self._rust_image.filter(mode, value)

    def alpha_composite(self, source: CanvasImage, dx: int, dy: int) -> None:
        """Alpha composite for this CanvasImage.
        
        Args:
            source: The source value. Expected type: `CanvasImage`.
            dx: The dx value. Expected type: `int`.
            dy: The dy value. Expected type: `int`.
        
        Returns:
            None.
        """
        self._rust_image.alpha_composite(source._rust_image, int(dx), int(dy))

    def to_rgba_bytes(self) -> bytes:
        """Return this CanvasImage converted to rgba bytes.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bytes`.
        """
        return bytes(self._rust_image.to_rgba_bytes())

    def save(self, path: str | Path) -> None:
        """Save for this CanvasImage.
        
        Args:
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            None.
        """
        self._rust_image.save(str(path))


__all__ = ["CanvasImage"]
