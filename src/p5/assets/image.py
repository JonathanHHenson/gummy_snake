"""Canvas-owned image abstraction and loading helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from p5.core.color import Color
from p5.exceptions import ArgumentValidationError


class _RustP5Image(Protocol):
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
    """Mutable RGBA image used by p5-py asset APIs."""

    _width: int
    _height: int
    _pixels: bytearray
    _version: int

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
            to_rgba_bytes = getattr(width, "to_rgba_bytes", None)
            tobytes = getattr(width, "tobytes", None)
            convert = getattr(width, "convert", None)
            source = convert("RGBA") if callable(convert) else width
            if callable(to_rgba_bytes):
                payload = bytes(to_rgba_bytes())
            elif callable(getattr(source, "tobytes", None)):
                payload = bytes(source.tobytes())
            elif callable(tobytes):
                payload = bytes(tobytes())
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

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def version(self) -> int:
        return self._version

    def to_rgba_bytes(self) -> bytes:
        return bytes(self._pixels)

    def tobytes(self) -> bytes:
        return self.to_rgba_bytes()

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
            self._version += 1
            return
        rgba = value.to_tuple() if isinstance(value, Color) else tuple(value)
        if len(rgba) == 3:
            rgba = (*rgba, 255)
        self._put_pixel(int(x), int(y), cast(tuple[int, int, int, int], rgba))
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
        resized = bytearray(target_width * target_height * 4)
        for y in range(target_height):
            sy = min(self.height - 1, int(y * self.height / target_height))
            for x in range(target_width):
                sx = min(self.width - 1, int(x * self.width / target_width))
                src = self._offset(sx, sy)
                dst = (y * target_width + x) * 4
                resized[dst : dst + 4] = self._pixels[src : src + 4]
        self._width = target_width
        self._height = target_height
        self._pixels = resized
        self._version += 1

    def mask(self, mask_image: Image) -> None:
        for y in range(self.height):
            for x in range(self.width):
                mx = min(mask_image.width - 1, int(x * mask_image.width / self.width))
                my = min(mask_image.height - 1, int(y * mask_image.height / self.height))
                mask = mask_image._pixel(mx, my)
                alpha = round(sum(mask[:3]) / 3 * (mask[3] / 255))
                offset = self._offset(x, y)
                self._pixels[offset + 3] = round(self._pixels[offset + 3] * alpha / 255)
        self._version += 1

    def filter(self, mode: str, value: float | None = None) -> None:
        from p5 import constants as c

        normalized = mode.lower()
        if normalized == c.GRAY:
            for offset in range(0, len(self._pixels), 4):
                gray = round(
                    self._pixels[offset] * 0.299
                    + self._pixels[offset + 1] * 0.587
                    + self._pixels[offset + 2] * 0.114
                )
                self._pixels[offset : offset + 3] = bytes((gray, gray, gray))
        elif normalized == c.INVERT:
            for offset in range(0, len(self._pixels), 4):
                self._pixels[offset] = 255 - self._pixels[offset]
                self._pixels[offset + 1] = 255 - self._pixels[offset + 1]
                self._pixels[offset + 2] = 255 - self._pixels[offset + 2]
        elif normalized == c.THRESHOLD:
            threshold = int(round((0.5 if value is None else value) * 255))
            for offset in range(0, len(self._pixels), 4):
                gray = round(
                    self._pixels[offset] * 0.299
                    + self._pixels[offset + 1] * 0.587
                    + self._pixels[offset + 2] * 0.114
                )
                bw = 255 if gray >= threshold else 0
                self._pixels[offset : offset + 3] = bytes((bw, bw, bw))
        elif normalized in {c.BLUR, c.POSTERIZE, c.ERODE, c.DILATE}:
            # The canvas runtime owns high quality image filters; keep these as
            # accepted no-ops for scripts that prepare images before drawing.
            pass
        else:
            raise ArgumentValidationError(f"Unsupported image filter {mode!r}.")
        self._version += 1

    def save(self, path: str | Path) -> None:
        P5Image.from_rgba_bytes(self.width, self.height, self.to_rgba_bytes()).save(path)

    def _crop(self, sx: int, sy: int, sw: int, sh: int) -> Image:
        cropped = bytearray(max(0, sw) * max(0, sh) * 4)
        for y in range(max(0, sh)):
            for x in range(max(0, sw)):
                if 0 <= sx + x < self.width and 0 <= sy + y < self.height:
                    src = self._offset(sx + x, sy + y)
                    dst = (y * sw + x) * 4
                    cropped[dst : dst + 4] = self._pixels[src : src + 4]
        return Image(sw, sh, cropped)

    def _alpha_composite(self, source: Image, dx: int, dy: int) -> None:
        for y in range(source.height):
            ty = dy + y
            if ty < 0 or ty >= self.height:
                continue
            for x in range(source.width):
                tx = dx + x
                if tx < 0 or tx >= self.width:
                    continue
                self._put_pixel(tx, ty, _alpha_over(self._pixel(tx, ty), source._pixel(x, y)))

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


def _alpha_over(
    destination: tuple[int, int, int, int],
    source: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    source_alpha = source[3] / 255.0
    if source_alpha <= 0.0:
        return destination
    destination_alpha = destination[3] / 255.0
    output_alpha = source_alpha + destination_alpha * (1.0 - source_alpha)
    if output_alpha <= 0.0:
        return (0, 0, 0, 0)
    rgb = []
    for index in range(3):
        value = (
            source[index] * source_alpha
            + destination[index] * destination_alpha * (1.0 - source_alpha)
        ) / output_alpha
        rgb.append(int(round(value)))
    return cast(tuple[int, int, int, int], (*rgb, int(round(output_alpha * 255.0))))


def load_image(path: str | Path) -> Image:
    image_path = Path(path)
    if not image_path.exists():
        raise ArgumentValidationError(f"Image file does not exist: {image_path!s}.")
    try:
        rust_image = P5Image.from_file(image_path)
    except Exception as exc:
        raise ArgumentValidationError(f"Could not load image {image_path!s}.") from exc
    return Image(rust_image.width, rust_image.height, rust_image.to_rgba_bytes())


def create_image(width: int, height: int) -> Image:
    return Image(int(width), int(height))


class P5Image:
    """Rust-managed image asset."""

    def __init__(self, rust_image: _RustP5Image) -> None:
        self._rust_image = rust_image

    @classmethod
    def from_file(cls, path: str | Path) -> P5Image:
        from p5.rust.canvas import require_canvas_extension

        return cls(require_canvas_extension().P5Image.from_file(str(path)))

    @classmethod
    def from_rgba_bytes(cls, width: int, height: int, pixels: bytes) -> P5Image:
        from p5.rust.canvas import require_canvas_extension

        return cls(require_canvas_extension().P5Image.from_rgba_bytes(width, height, pixels))

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


__all__ = ["Image", "P5Image", "load_image", "create_image"]
