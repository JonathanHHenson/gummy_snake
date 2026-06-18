"""Pillow-backed Image abstraction and loading helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from PIL import Image as PILImage
from PIL import ImageChops, ImageFilter, ImageOps

from p5 import constants as c
from p5.core.color import Color
from p5.exceptions import ArgumentValidationError


class _RustP5Image(Protocol):
    width: int
    height: int
    version: int

    def save(self, path: str) -> None: ...

    def to_rgba_bytes(self) -> bytes: ...


@dataclass(slots=True)
class Image:
    _image: PILImage.Image
    _version: int

    def __init__(self, image: PILImage.Image) -> None:
        self._image = image.convert("RGBA")
        self._version = 0

    @property
    def width(self) -> int:
        return self._image.width

    @property
    def height(self) -> int:
        return self._image.height

    @property
    def pillow(self) -> PILImage.Image:
        return self._image

    @property
    def version(self) -> int:
        return self._version

    def copy(self, *args: int) -> Image:
        if not args:
            return Image(self._image.copy())
        if len(args) == 4:
            sx, sy, sw, sh = args
            return Image(self._image.crop((sx, sy, sx + sw, sy + sh)))
        if len(args) == 8:
            sx, sy, sw, sh, _dx, _dy, dw, dh = args
            return Image(self._image.crop((sx, sy, sx + sw, sy + sh)).resize((dw, dh)))
        raise ArgumentValidationError("Image.copy() accepts 0, 4, or 8 integer arguments.")

    def get(
        self, x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None
    ):
        if x is None and y is None:
            return self.copy()
        if x is None or y is None:
            raise ArgumentValidationError("Image.get() requires both x and y.")
        ix = int(x)
        iy = int(y)
        if w is None and h is None:
            rgba = cast(tuple[int, int, int, int], self._image.getpixel((ix, iy)))
            return Color(*rgba)
        if w is None or h is None:
            raise ArgumentValidationError("Image.get() requires both width and height for regions.")
        iw = int(w)
        ih = int(h)
        return Image(self._image.crop((ix, iy, ix + iw, iy + ih)))

    def set(
        self,
        x: int,
        y: int,
        value: Color | tuple[int, int, int] | tuple[int, int, int, int] | Image,
    ) -> None:
        if isinstance(value, Image):
            self._image.alpha_composite(value.pillow, (int(x), int(y)))
            self._version += 1
            return
        rgba = value.to_tuple() if isinstance(value, Color) else tuple(value)
        if len(rgba) == 3:
            rgba = (*rgba, 255)
        self._image.putpixel((int(x), int(y)), rgba)
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
        self._image = self._image.resize((target_width, target_height), PILImage.Resampling.LANCZOS)
        self._version += 1

    def mask(self, mask_image: Image) -> None:
        alpha = mask_image.pillow.convert("L").resize(self._image.size)
        self._image.putalpha(ImageChops.multiply(self._image.getchannel("A"), alpha))
        self._version += 1

    def filter(self, mode: str, value: float | None = None) -> None:
        normalized = mode.lower()
        if normalized == c.GRAY:
            alpha = self._image.getchannel("A")
            self._image = ImageOps.grayscale(self._image).convert("RGBA")
            self._image.putalpha(alpha)
        elif normalized == c.THRESHOLD:
            threshold = int(round((0.5 if value is None else value) * 255))
            alpha = self._image.getchannel("A")

            def threshold_pixel(px: Any) -> int:
                return 255 if int(px) >= threshold else 0

            gray = ImageOps.grayscale(self._image).point(threshold_pixel)
            self._image = PILImage.merge("RGBA", (gray, gray, gray, alpha))
        elif normalized == c.INVERT:
            rgb = ImageOps.invert(self._image.convert("RGB"))
            self._image = rgb.convert("RGBA")
        elif normalized == c.BLUR:
            radius = 1 if value is None else float(value)
            self._image = self._image.filter(ImageFilter.GaussianBlur(radius))
        elif normalized == c.POSTERIZE:
            bits = max(1, min(8, int(value or 4)))
            self._image = ImageOps.posterize(self._image.convert("RGB"), bits).convert("RGBA")
        elif normalized == c.ERODE:
            self._image = self._image.filter(ImageFilter.MinFilter(3))
        elif normalized == c.DILATE:
            self._image = self._image.filter(ImageFilter.MaxFilter(3))
        else:
            raise ArgumentValidationError(f"Unsupported image filter {mode!r}.")
        self._version += 1

    def save(self, path: str | Path) -> None:
        self._image.save(path)


def load_image(path: str | Path) -> Image:
    image_path = Path(path)
    if not image_path.exists():
        raise ArgumentValidationError(f"Image file does not exist: {image_path!s}.")
    try:
        with PILImage.open(image_path) as image:
            return Image(image.copy())
    except OSError as exc:
        raise ArgumentValidationError(f"Could not load image {image_path!s}.") from exc


def create_image(width: int, height: int) -> Image:
    if width <= 0 or height <= 0:
        raise ArgumentValidationError("create_image() dimensions must be positive.")
    return Image(PILImage.new("RGBA", (int(width), int(height)), (0, 0, 0, 0)))


class P5Image:
    """Rust-managed image asset with Pillow import/export compatibility."""

    def __init__(self, rust_image: _RustP5Image) -> None:
        self._rust_image = rust_image

    @classmethod
    def from_file(cls, path: str | Path) -> P5Image:
        from p5.rust.canvas import require_canvas_extension

        return cls(require_canvas_extension().P5Image.from_file(str(path)))

    @classmethod
    def from_pil(cls, image: PILImage.Image) -> P5Image:
        from p5.rust.canvas import require_canvas_extension

        rgba = image.convert("RGBA")
        rust_image = require_canvas_extension().P5Image.from_rgba_bytes(
            rgba.width,
            rgba.height,
            rgba.tobytes(),
        )
        return cls(rust_image)

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
    def pillow(self) -> PILImage.Image:
        return self.to_pil()

    def to_pil(self) -> PILImage.Image:
        pixels = bytes(self._rust_image.to_rgba_bytes())
        return PILImage.frombytes("RGBA", (self.width, self.height), pixels)

    def save(self, path: str | Path) -> None:
        self._rust_image.save(str(path))


__all__ = ["Image", "P5Image", "load_image", "create_image"]
