"""Public Image model backed by canvas image operations."""

from __future__ import annotations

from collections.abc import Buffer
from dataclasses import dataclass
from pathlib import Path
from typing import Self, cast, overload

from gummysnake import constants as c
from gummysnake.assets.image.canvas import CanvasImage
from gummysnake.assets.image.deferred import ImageDeferredMixin
from gummysnake.assets.image.exporting import png_export_path
from gummysnake.assets.image.source import ImageSource, coerce_image_source
from gummysnake.core.color import Color
from gummysnake.exceptions import ArgumentValidationError, UnsupportedFeatureError


@dataclass(slots=True)
class Image(ImageDeferredMixin):
    """Mutable RGBA image used by Gummy Snake asset APIs.

    The public Image API remains Pythonic, while pixel storage and bulk image
    operations are owned by the Rust canvas runtime through CanvasImage.
    """

    _rust_image: CanvasImage

    def __init__(
        self,
        width: int | ImageSource | CanvasImage,
        height: int | None = None,
        pixels: bytes | bytearray | None = None,
    ) -> None:
        """Create an image from dimensions, encoded/source data, or a canvas handle."""
        if isinstance(width, CanvasImage):
            self._rust_image = width
            return
        image_width, image_height, payload = coerce_image_source(width, height, pixels)
        expected = image_width * image_height * 4
        if len(payload) != expected:
            raise ArgumentValidationError(
                f"Image pixel buffer must contain {expected} bytes, got {len(payload)}."
            )
        self._rust_image = CanvasImage.from_rgba_bytes(image_width, image_height, payload)

    @classmethod
    def from_rust_image(cls, image: CanvasImage) -> Self:
        """Wrap a Rust-owned canvas image handle in the public ``Image`` class.

        Args:
            image: Canvas image handle created by the Rust runtime.

        Returns:
            An ``Image`` that uses the same underlying pixel storage.
        """

        return cls(image)

    @property
    def width(self) -> int:
        """Image width in pixels."""

        return self._rust_image.width

    @property
    def height(self) -> int:
        """Image height in pixels."""

        return self._rust_image.height

    @property
    def version(self) -> int:
        """Change counter that increases when this image's pixels are modified."""

        return self._rust_image.version

    @property
    def cache_key(self) -> int:
        """Stable key used by renderer caches for this Rust-owned image."""

        return self._rust_image.cache_key

    @property
    def rust_image(self) -> CanvasImage:
        """Canvas image handle used internally by the Rust runtime."""

        return self._rust_image

    def to_rgba_bytes(self) -> bytes:
        """Return the image pixels as packed RGBA bytes.

        Returns:
            A ``bytes`` object containing red, green, blue, and alpha bytes for each pixel.
        """

        return self._rust_image.to_rgba_bytes()

    def tobytes(self) -> bytes:
        """Return the image pixels as packed RGBA bytes.

        Returns:
            The same byte layout as ``to_rgba_bytes()``.
        """

        return self.to_rgba_bytes()

    @property
    def pixels(self) -> list[int]:
        """Image pixels as a mutable-style list of RGBA byte values."""

        return list(self.to_rgba_bytes())

    @overload
    def __getitem__(self, key: tuple[int, int]) -> Color: ...

    @overload
    def __getitem__(self, key: tuple[slice, slice]) -> Image: ...

    def __getitem__(self, key: tuple[int, int] | tuple[slice, slice]) -> Color | Image:
        """Read one pixel or crop a rectangular region with index syntax.

        Args:
            key: ``(x, y)`` for one pixel, or ``(x_slice, y_slice)`` for an image region.

        Returns:
            A ``Color`` for one pixel, or a new ``Image`` for a sliced region.
        """

        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("Image indices must be (x, y) or (x_slice, y_slice).")
        x_key, y_key = key
        if isinstance(x_key, slice) or isinstance(y_key, slice):
            if not isinstance(x_key, slice) or not isinstance(y_key, slice):
                raise TypeError("Image region access requires two slices.")
            x, w = self._slice_region(x_key, self.width)
            y, h = self._slice_region(y_key, self.height)
            return self._crop(x, y, w, h)
        return self.get(int(cast(int, x_key)), int(cast(int, y_key)))

    def __setitem__(
        self,
        key: tuple[int, int],
        value: Color | tuple[int, int, int] | tuple[int, int, int, int] | Image,
    ) -> None:
        """Set one pixel with index assignment.

        Args:
            key: ``(x, y)`` pixel coordinate to modify.
            value: Color, RGB/RGBA tuple, or image to composite at that coordinate.
        """

        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("Image assignment indices must be (x, y).")
        x_key, y_key = key
        if isinstance(x_key, slice) or isinstance(y_key, slice):
            raise TypeError("Image region assignment is not supported; assign pixels individually.")
        self.set(int(cast(int, x_key)), int(cast(int, y_key)), value)

    def load_pixels(self) -> list[int]:
        """Return image pixels as RGBA byte values.

        Returns:
            A list containing four integer byte values for each pixel.
        """

        return self.pixels

    def update_pixels(self, pixels: Buffer | list[int] | tuple[int, ...] | None = None) -> None:
        """Replace all image pixels from an RGBA byte buffer.

        Args:
            pixels: Buffer or sequence containing exactly ``width * height * 4`` byte values.
                Passing ``None`` leaves the image unchanged.
        """

        if pixels is None:
            return
        try:
            payload = bytes(pixels)
        except ValueError as exc:
            raise ArgumentValidationError(
                "Image pixel values must be integers between 0 and 255."
            ) from exc
        expected = self.width * self.height * 4
        if len(payload) != expected:
            raise ArgumentValidationError(
                f"Image pixel buffer must contain {expected} bytes, got {len(payload)}."
            )
        self._rust_image.replace_rgba_bytes(payload)

    def pixel_density(self, value: float | None = None) -> float:
        """Return or validate the image pixel density.

        Args:
            value: Optional requested density. Only ``1.0`` is currently supported for images.

        Returns:
            The image density, currently always ``1.0``.
        """

        if value is None or value == 1:
            return 1.0
        raise UnsupportedFeatureError(
            "Image.pixel_density() only supports density 1.0. Image HiDPI buffers are "
            "deferred until the Rust canvas runtime exposes image-level density semantics."
        )

    @overload
    def copy(self) -> Image: ...

    @overload
    def copy(self, sx: int, sy: int, sw: int, sh: int, /) -> Image: ...

    @overload
    def copy(
        self, sx: int, sy: int, sw: int, sh: int, dx: int, dy: int, dw: int, dh: int, /
    ) -> Image: ...

    def copy(self, *args: int) -> Image:
        """Copy this image or a region of it.

        Args:
            args: No arguments copies the whole image. Four integers copy ``sx, sy, sw, sh``.
                Eight integers copy and resize ``sx, sy, sw, sh`` to ``dw, dh``.

        Returns:
            A new ``Image`` containing the copied pixels.
        """

        if not args:
            return Image(self._rust_image.copy())
        if len(args) == 4:
            return self._crop(*(int(value) for value in args))
        if len(args) == 8:
            sx, sy, sw, sh, _dx, _dy, dw, dh = (int(value) for value in args)
            cropped = self._crop(sx, sy, sw, sh)
            cropped.resize(dw, dh)
            return cropped
        raise ArgumentValidationError("Image.copy() accepts 0, 4, or 8 integer arguments.")

    @overload
    def get(self) -> Image: ...

    @overload
    def get(self, x: int, y: int) -> Color: ...

    @overload
    def get(self, x: int, y: int, w: int, h: int) -> Image: ...

    def get(
        self, x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None
    ) -> Color | Image:
        """Read a pixel, copy the whole image, or crop a region.

        Args:
            x: Left pixel coordinate, or omitted to copy the whole image.
            y: Top pixel coordinate, required when ``x`` is provided.
            w: Region width when cropping.
            h: Region height when cropping.

        Returns:
            A ``Color`` for one pixel, or a new ``Image`` for whole-image and region copies.
        """

        if x is None and y is None:
            return self.copy()
        if x is None or y is None:
            raise ArgumentValidationError("Image.get() requires both x and y.")
        if w is None and h is None:
            return Color(*self._pixel(int(x), int(y)))
        if w is None or h is None:
            raise ArgumentValidationError("Image.get() requires both width and height for regions.")
        return self._crop(int(x), int(y), int(w), int(h))

    def set(
        self,
        x: int,
        y: int,
        value: Color | tuple[int, int, int] | tuple[int, int, int, int] | Image,
    ) -> None:
        """Set a pixel or composite another image at a coordinate.

        Args:
            x: Horizontal pixel coordinate.
            y: Vertical pixel coordinate.
            value: Color, RGB/RGBA tuple, or image to composite with alpha.
        """

        if isinstance(value, Image):
            self._rust_image.alpha_composite(value._rust_image, int(x), int(y))
            return
        rgba = value.to_tuple() if isinstance(value, Color) else tuple(value)
        if len(rgba) == 3:
            rgba = (*rgba, 255)
        self._put_pixel(int(x), int(y), cast(tuple[int, int, int, int], rgba))

    def resize(self, width: int, height: int) -> None:
        """Resize this image in place.

        Args:
            width: New width in pixels. Use ``0`` to preserve aspect ratio from ``height``.
            height: New height in pixels. Use ``0`` to preserve aspect ratio from ``width``.
        """

        target_width = self.width if width == 0 else int(width)
        target_height = self.height if height == 0 else int(height)
        if width == 0 and height != 0:
            target_width = round(self.width * target_height / self.height)
        if height == 0 and width != 0:
            target_height = round(self.height * target_width / self.width)
        if target_width <= 0 or target_height <= 0:
            raise ArgumentValidationError(
                "Image.resize() dimensions must be positive or one zero for aspect ratio."
            )
        self._rust_image.resize(target_width, target_height)

    def mask(self, mask_image: Image) -> None:
        """Apply another image's alpha channel as a mask.

        Args:
            mask_image: Image whose alpha values control this image's transparency.
        """

        self._rust_image.mask(mask_image._rust_image)

    def filter(self, mode: c.ImageFilter, value: float | None = None) -> None:
        """Apply an image filter in place.

        Args:
            mode: Filter to apply, such as ``GRAY``, ``INVERT``, or ``BLUR``.
            value: Optional filter strength or threshold used by filters that need one.
        """

        normalized = mode.value
        if normalized not in {
            c.GRAY,
            c.INVERT,
            c.THRESHOLD,
            c.BLUR,
            c.POSTERIZE,
            c.ERODE,
            c.DILATE,
        }:
            raise ArgumentValidationError(f"Unsupported image filter {mode!r}.")
        self._rust_image.filter(normalized, value)

    def save(self, path: str | Path) -> None:
        """Save this image as a PNG file.

        Args:
            path: Destination path. A suffixless path receives a ``.png`` suffix.
        """

        self._rust_image.save(str(png_export_path(path, operation="Image.save()")))

    def _crop(self, sx: int, sy: int, sw: int, sh: int) -> Image:
        if sw <= 0 or sh <= 0:
            raise ArgumentValidationError("Image region dimensions must be positive.")
        return Image(self._rust_image.crop(sx, sy, sw, sh))

    def _offset(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ArgumentValidationError("Pixel coordinates are outside the image bounds.")
        return (y * self.width + x) * 4

    def _pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        self._offset(x, y)
        return self._rust_image.get_pixel(x, y)

    def _put_pixel(self, x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        self._offset(x, y)
        clamped = tuple(max(0, min(255, int(value))) for value in rgba)
        self._rust_image.set_pixel(x, y, cast(tuple[int, int, int, int], clamped))

    @staticmethod
    def _slice_region(value: slice, size: int) -> tuple[int, int]:
        start, stop, step = value.indices(size)
        if step != 1:
            raise ValueError("Image region slices do not support steps.")
        return start, max(0, stop - start)


__all__ = ["Image"]
