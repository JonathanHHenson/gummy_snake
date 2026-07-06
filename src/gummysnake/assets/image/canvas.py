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
        """Load an image file through the Rust canvas runtime.

        Args:
            path: Image file to read.

        Returns:
            A Rust-managed canvas image handle.
        """

        from gummysnake.rust.canvas import require_canvas_runtime

        return cls(
            cast(_RustCanvasImage, require_canvas_runtime().CanvasImage.from_file(str(path)))
        )

    @classmethod
    def from_rgba_bytes(cls, width: int, height: int, pixels: bytes) -> CanvasImage:
        """Create an image from packed RGBA bytes.

        Args:
            width: Image width in pixels.
            height: Image height in pixels.
            pixels: RGBA byte payload with four bytes per pixel.

        Returns:
            A Rust-managed canvas image handle.
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
        """Image width in pixels."""

        return int(self._rust_image.width)

    @property
    def height(self) -> int:
        """Image height in pixels."""

        return int(self._rust_image.height)

    @property
    def version(self) -> int:
        """Change counter from the Rust image handle."""

        return int(self._rust_image.version)

    @property
    def cache_key(self) -> int:
        """Stable renderer-cache key for this image handle."""

        return int(self._rust_image.key)

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        """Return one pixel as an ``(r, g, b, a)`` tuple.

        Args:
            x: Horizontal pixel coordinate.
            y: Vertical pixel coordinate.

        Returns:
            Four 8-bit color channel values.
        """

        r, g, b, a = self._rust_image.get_pixel(int(x), int(y))
        return int(r), int(g), int(b), int(a)

    def set_pixel(self, x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        """Set one pixel from an ``(r, g, b, a)`` tuple.

        Args:
            x: Horizontal pixel coordinate.
            y: Vertical pixel coordinate.
            rgba: Four 8-bit color channel values.
        """

        r, g, b, a = rgba
        self._rust_image.set_pixel(int(x), int(y), int(r), int(g), int(b), int(a))

    def replace_rgba_bytes(self, pixels: bytes) -> None:
        """Replace every pixel from packed RGBA bytes.

        Args:
            pixels: Byte payload with exactly four bytes per pixel.
        """

        self._rust_image.replace_rgba_bytes(pixels)

    def copy(self) -> Self:
        """Return a new handle containing a copy of this image."""

        return type(self)(self._rust_image.copy())

    def crop(self, sx: int, sy: int, sw: int, sh: int) -> Self:
        """Return a cropped copy of this image.

        Args:
            sx: Source x coordinate.
            sy: Source y coordinate.
            sw: Source width in pixels.
            sh: Source height in pixels.

        Returns:
            A new image handle for the cropped region.
        """

        return type(self)(self._rust_image.crop(int(sx), int(sy), int(sw), int(sh)))

    def resize(self, width: int, height: int) -> None:
        """Resize the image in place.

        Args:
            width: New width in pixels.
            height: New height in pixels.
        """

        self._rust_image.resize(int(width), int(height))

    def mask(self, mask: CanvasImage) -> None:
        """Apply another image's alpha channel as a mask.

        Args:
            mask: Image whose alpha values control this image's transparency.
        """

        self._rust_image.mask(mask._rust_image)

    def filter(self, mode: str, value: float | None) -> None:
        """Apply a Rust canvas image filter in place.

        Args:
            mode: Runtime filter name.
            value: Optional filter parameter used by filters that need one.
        """

        self._rust_image.filter(mode, value)

    def alpha_composite(self, source: CanvasImage, dx: int, dy: int) -> None:
        """Composite another image over this one using alpha blending.

        Args:
            source: Image to draw over this image.
            dx: Destination x coordinate.
            dy: Destination y coordinate.
        """

        self._rust_image.alpha_composite(source._rust_image, int(dx), int(dy))

    def to_rgba_bytes(self) -> bytes:
        """Return packed RGBA pixel bytes from the Rust image."""

        return bytes(self._rust_image.to_rgba_bytes())

    def save(self, path: str | Path) -> None:
        """Save this image to a file.

        Args:
            path: Destination path. The extension selects the image format.
        """

        self._rust_image.save(str(path))


__all__ = ["CanvasImage"]
