"""Canvas-owned image abstraction and loading helpers."""

from __future__ import annotations

from collections.abc import Buffer
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Any, Protocol, Self, cast

from gummysnake import constants as c
from gummysnake.assets._paths import resolve_asset_path
from gummysnake.core.color import Color
from gummysnake.exceptions import ArgumentValidationError, UnsupportedFeatureError

_IMAGE_CACHE_KEYS = count(1)


class _RustCanvasImage(Protocol):
    width: int
    height: int
    version: int

    def save(self, path: str) -> None: ...

    def to_rgba_bytes(self) -> bytes: ...


class _ImageSource(Protocol):
    width: int
    height: int

    def tobytes(self) -> bytes: ...


@dataclass(slots=True)
class Image:
    """Mutable RGBA image used by Gummy Snake asset APIs."""

    _width: int
    _height: int
    _pixels: bytearray
    _version: int
    _cache_key: int
    _rust_image: CanvasImage | None

    def __init__(
        self,
        width: int | _ImageSource,
        height: int | None = None,
        pixels: bytes | bytearray | None = None,
    ) -> None:
        if isinstance(width, int):
            if height is None:
                raise ArgumentValidationError("Image height is required.")
            image_width = int(width)
            image_height = int(height)
            if image_width <= 0 or image_height <= 0:
                raise ArgumentValidationError("Image dimensions must be positive.")
            payload = bytes(pixels or b"\x00" * (image_width * image_height * 4))
        else:
            image_width = int(width.width)
            image_height = int(width.height)
            to_rgba_bytes: Any = getattr(width, "to_rgba_bytes", None)
            tobytes: Any = getattr(width, "tobytes", None)
            convert: Any = getattr(width, "convert", None)
            source = convert("RGBA") if callable(convert) else width
            if callable(to_rgba_bytes):
                payload = bytes(cast(Any, to_rgba_bytes)())
            else:
                source_tobytes: Any = getattr(source, "tobytes", None)
                if callable(source_tobytes):
                    payload = bytes(cast(Any, source_tobytes)())
                elif callable(tobytes):
                    payload = bytes(cast(Any, tobytes)())
                else:
                    raise ArgumentValidationError("Image source must expose RGBA bytes.")
        expected = image_width * image_height * 4
        if len(payload) != expected:
            raise ArgumentValidationError(
                f"Image pixel buffer must contain {expected} bytes, got {len(payload)}."
            )
        self._width = image_width
        self._height = image_height
        self._pixels = bytearray(payload)
        self._version = 0
        self._cache_key = next(_IMAGE_CACHE_KEYS)
        self._rust_image = width if isinstance(width, CanvasImage) else None

    @classmethod
    def from_rust_image(cls, image: CanvasImage) -> Self:
        loaded = cls(image.width, image.height, image.to_rgba_bytes())
        loaded._rust_image = image
        return loaded

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def version(self) -> int:
        return self._version

    @property
    def cache_key(self) -> int:
        return self._cache_key

    @property
    def rust_image(self) -> CanvasImage | None:
        return self._rust_image

    def to_rgba_bytes(self) -> bytes:
        return bytes(self._pixels)

    def tobytes(self) -> bytes:
        return self.to_rgba_bytes()

    @property
    def pixels(self) -> list[int]:
        return list(self._pixels)

    def __getitem__(self, key: object):
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
        key: object,
        value: Color | tuple[int, int, int] | tuple[int, int, int, int] | Image,
    ) -> None:
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("Image assignment indices must be (x, y).")
        x_key, y_key = key
        if isinstance(x_key, slice) or isinstance(y_key, slice):
            raise TypeError("Image region assignment is not supported; assign pixels individually.")
        self.set(int(cast(int, x_key)), int(cast(int, y_key)), value)

    def load_pixels(self) -> list[int]:
        return self.pixels

    def update_pixels(self, pixels: Buffer | list[int] | tuple[int, ...] | None = None) -> None:
        if pixels is not None:
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
            self._pixels = bytearray(payload)
        self._rust_image = None
        self._version += 1

    def pixel_density(self, value: float | None = None) -> float:
        if value is None or value == 1:
            return 1.0
        raise UnsupportedFeatureError(
            "Image.pixel_density() only supports density 1.0. Image HiDPI buffers are "
            "deferred until the Rust canvas runtime exposes image-level density semantics."
        )

    def copy(self, *args: int) -> Image:
        if not args:
            return Image(self.width, self.height, self.to_rgba_bytes())
        if len(args) == 4:
            sx, sy, sw, sh = (int(value) for value in args)
            return self._crop(sx, sy, sw, sh)
        if len(args) == 8:
            sx, sy, sw, sh, _dx, _dy, dw, dh = (int(value) for value in args)
            cropped = self._crop(sx, sy, sw, sh)
            cropped.resize(dw, dh)
            return cropped
        raise ArgumentValidationError("Image.copy() accepts 0, 4, or 8 integer arguments.")

    def get(
        self, x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None
    ):
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
        if isinstance(value, Image):
            self._alpha_composite(value, int(x), int(y))
            self._rust_image = None
            self._version += 1
            return
        rgba = value.to_tuple() if isinstance(value, Color) else tuple(value)
        if len(rgba) == 3:
            rgba = (*rgba, 255)
        self._put_pixel(int(x), int(y), cast(tuple[int, int, int, int], rgba))
        self._rust_image = None
        self._version += 1

    def resize(self, width: int, height: int) -> None:
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
        source_width = self.width
        source_height = self.height
        source_pixels = self.to_rgba_bytes()
        self._pixels = bytearray(
            _canvas_module().image_resize_rgba(
                source_width,
                source_height,
                source_pixels,
                target_width,
                target_height,
            )
        )
        self._width = target_width
        self._height = target_height
        self._rust_image = None
        self._version += 1

    def mask(self, mask_image: Image) -> None:
        self._pixels = bytearray(
            _canvas_module().image_mask_rgba(
                self.width,
                self.height,
                self.to_rgba_bytes(),
                mask_image.width,
                mask_image.height,
                mask_image.to_rgba_bytes(),
            )
        )
        self._rust_image = None
        self._version += 1

    def filter(self, mode: c.ImageFilter, value: float | None = None) -> None:
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
        self._pixels = bytearray(
            _canvas_module().image_filter_rgba(
                self.width,
                self.height,
                self.to_rgba_bytes(),
                normalized,
                value,
            )
        )
        self._rust_image = None
        self._version += 1

    def blend(self, *args: object) -> None:
        raise UnsupportedFeatureError(
            "Image.blend() is deferred. Use canvas-level blend(...) for Rust-backed region "
            "blending until image-local blend modes are implemented."
        )

    def delay(self, *args: object) -> None:
        raise UnsupportedFeatureError(
            "Animated image frame delay controls are deferred because Gummy Snake currently loads "
            "images as single RGBA frames through the Rust canvas runtime."
        )

    def get_current_frame(self) -> int:
        raise UnsupportedFeatureError(
            "Animated image frame controls are deferred because Gummy Snake currently loads images "
            "as single RGBA frames through the Rust canvas runtime."
        )

    def num_frames(self) -> int:
        return 1

    def play(self) -> None:
        raise UnsupportedFeatureError(
            "Animated image playback is deferred because Gummy Snake currently loads images as "
            "single RGBA frames through the Rust canvas runtime."
        )

    def pause(self) -> None:
        raise UnsupportedFeatureError(
            "Animated image playback is deferred because Gummy Snake currently loads images as "
            "single RGBA frames through the Rust canvas runtime."
        )

    def reset(self) -> None:
        raise UnsupportedFeatureError(
            "Animated image frame controls are deferred because Gummy Snake currently loads images "
            "as single RGBA frames through the Rust canvas runtime."
        )

    def set_frame(self, frame: int) -> None:
        if int(frame) == 0:
            return None
        raise UnsupportedFeatureError(
            "Animated image frame controls are deferred because Gummy Snake currently loads images "
            "as single RGBA frames through the Rust canvas runtime."
        )

    def save(self, path: str | Path) -> None:
        CanvasImage.from_rgba_bytes(self.width, self.height, self.to_rgba_bytes()).save(path)

    def _crop(self, sx: int, sy: int, sw: int, sh: int) -> Image:
        target_width = max(0, sw)
        target_height = max(0, sh)
        if target_width == 0 or target_height == 0:
            raise ArgumentValidationError("Image region dimensions must be positive.")
        cropped = _canvas_module().image_crop_rgba(
            self.width,
            self.height,
            self.to_rgba_bytes(),
            sx,
            sy,
            target_width,
            target_height,
        )
        return Image(target_width, target_height, cropped)

    def _alpha_composite(self, source: Image, dx: int, dy: int) -> None:
        self._pixels = bytearray(
            _canvas_module().image_alpha_composite_rgba(
                self.width,
                self.height,
                self.to_rgba_bytes(),
                source.width,
                source.height,
                source.to_rgba_bytes(),
                dx,
                dy,
            )
        )

    def _offset(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ArgumentValidationError("Pixel coordinates are outside the image bounds.")
        return (y * self.width + x) * 4

    def _pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        offset = self._offset(x, y)
        return cast(tuple[int, int, int, int], tuple(self._pixels[offset : offset + 4]))

    def _put_pixel(self, x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        offset = self._offset(x, y)
        self._pixels[offset : offset + 4] = bytes(max(0, min(255, int(value))) for value in rgba)

    @staticmethod
    def _slice_region(value: slice, size: int) -> tuple[int, int]:
        start, stop, step = value.indices(size)
        if step != 1:
            raise ValueError("Image region slices do not support steps.")
        return start, max(0, stop - start)


def _canvas_module() -> Any:
    from gummysnake.rust.canvas import require_canvas_extension

    return require_canvas_extension()


def load_image(path: str | Path) -> Image:
    image_path = resolve_asset_path(path)
    if not image_path.exists():
        raise ArgumentValidationError(f"Image file does not exist: {image_path!s}.")
    try:
        rust_image = CanvasImage.from_file(image_path)
    except Exception as exc:
        raise ArgumentValidationError(f"Could not load image {image_path!s}.") from exc
    return Image.from_rust_image(rust_image)


async def load_image_async(path: str | Path) -> Image:
    return load_image(path)


def create_image(width: int, height: int) -> Image:
    return Image(int(width), int(height))


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


__all__ = ["Image", "CanvasImage", "load_image", "load_image_async", "create_image"]
