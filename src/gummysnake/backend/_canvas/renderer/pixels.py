"""Pixel and export operations for the Rust canvas renderer."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import Any, cast

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.backend._canvas.renderer._protocols import CanvasRendererHost
from gummysnake.exceptions import ArgumentValidationError


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


class PixelBuffer(bytearray):
    _dirty_start: int | None
    _dirty_end: int | None

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        self._dirty_start = None
        self._dirty_end = None

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        if isinstance(key, slice):
            start, stop, _step = key.indices(len(self))
            self._mark_dirty(start, stop)
        else:
            index = key if key >= 0 else len(self) + key
            self._mark_dirty(index, index + 1)

    def __getitem__(self, key: Any) -> Any:
        value = super().__getitem__(key)
        if isinstance(key, slice):
            return list(value)
        return value

    def __eq__(self, value: object) -> bool:
        if isinstance(value, list | tuple):
            return len(self) == len(value) and all(
                left == right for left, right in zip(self, value, strict=True)
            )
        return super().__eq__(value)

    def dirty_range(self) -> tuple[int, int] | None:
        if self._dirty_start is None or self._dirty_end is None:
            return None
        return self._dirty_start, self._dirty_end

    def clear_dirty(self) -> None:
        self._dirty_start = None
        self._dirty_end = None

    def _mark_dirty(self, start: int, end: int) -> None:
        if end <= start:
            return
        self._dirty_start = start if self._dirty_start is None else min(self._dirty_start, start)
        self._dirty_end = end if self._dirty_end is None else max(self._dirty_end, end)


class CanvasRendererPixelsMixin:
    def load_pixels(self) -> list[int]:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("pixel_readbacks")
        callback = getattr(_renderer(self)._require_canvas(), "load_pixel_bytes", None)
        if callable(callback):
            pixels = _renderer(self)._call("pixel byte readback", callback)
        else:
            pixels = _renderer(self)._call(
                "pixel readback", _renderer(self)._require_canvas().load_pixels
            )
        return cast(list[int], PixelBuffer(pixels))

    def load_pixel_bytes(self) -> bytes:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("pixel_readbacks")
        callback = getattr(_renderer(self)._require_canvas(), "load_pixel_bytes", None)
        if callable(callback):
            pixels = _renderer(self)._call("pixel byte readback", callback)
            if isinstance(pixels, bytes):
                return pixels
            return bytes(cast(Buffer | Sequence[int], pixels))
        pixels = cast(
            Buffer | Sequence[int],
            _renderer(self)._call("pixel readback", _renderer(self)._require_canvas().load_pixels),
        )
        return bytes(pixels)

    def load_pixel_region(self, x: int, y: int, width: int, height: int) -> bytes:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("pixel_readbacks")
        return bytes(
            _renderer(self)._call(
                "pixel region readback",
                _renderer(self)._require_canvas().load_pixel_region,
                int(x),
                int(y),
                int(width),
                int(height),
            )
        )

    def update_pixels(self, pixels: Sequence[int] | Buffer) -> None:
        _renderer(self)._flush_line_batch()
        if isinstance(pixels, PixelBuffer) and self._upload_dirty_pixel_range(pixels):
            pixels.clear_dirty()
            return
        payload = self._pixel_payload(pixels)
        _renderer(self)._count("pixel_uploads")
        callback = (
            getattr(_renderer(self)._require_canvas(), "update_pixel_buffer", None)
            if payload is pixels
            else None
        )
        if callable(callback):
            _renderer(self)._call("pixel buffer upload", callback, payload)
            if isinstance(pixels, PixelBuffer):
                pixels.clear_dirty()
            return
        _renderer(self)._call(
            "pixel upload", _renderer(self)._require_canvas().update_pixels, payload
        )
        if isinstance(pixels, PixelBuffer):
            pixels.clear_dirty()

    def set_pixel_rgba(self, x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("pixel_uploads")
        callback = getattr(_renderer(self)._require_canvas(), "set_pixel_rgba", None)
        if callable(callback):
            _renderer(self)._call(
                "pixel write",
                callback,
                int(x),
                int(y),
                tuple(max(0, min(255, int(channel))) for channel in rgba),
            )
            return
        _renderer(self)._call(
            "pixel region upload",
            _renderer(self)._require_canvas().update_pixel_region,
            bytes(max(0, min(255, int(channel))) for channel in rgba),
            1,
            1,
            int(x),
            int(y),
            False,
        )

    def update_pixel_region(
        self,
        pixels: Sequence[int] | Buffer,
        width: int,
        height: int,
        x: int,
        y: int,
        *,
        alpha_composite: bool = True,
    ) -> None:
        _renderer(self)._flush_line_batch()
        payload = self._pixel_payload(pixels)
        _renderer(self)._count("pixel_uploads")
        callback = (
            getattr(_renderer(self)._require_canvas(), "update_pixel_region_buffer", None)
            if payload is pixels
            else None
        )
        if callable(callback):
            _renderer(self)._call(
                "pixel region buffer upload",
                callback,
                payload,
                int(width),
                int(height),
                int(x),
                int(y),
                alpha_composite,
            )
            return
        _renderer(self)._call(
            "pixel region upload",
            _renderer(self)._require_canvas().update_pixel_region,
            payload,
            int(width),
            int(height),
            int(x),
            int(y),
            alpha_composite,
        )

    def adjust_pixel_prefix(
        self,
        byte_limit: int,
        stride: int,
        red_delta: int,
        green_delta: int,
    ) -> None:
        _renderer(self)._flush_line_batch()
        callback = getattr(_renderer(self)._require_canvas(), "adjust_pixel_prefix", None)
        if not callable(callback):
            raise ArgumentValidationError(
                "The installed canvas runtime cannot adjust pixel prefixes."
            )
        _renderer(self)._count("gpu_region_effect_passes")
        _renderer(self)._call(
            "pixel prefix adjustment",
            callback,
            int(byte_limit),
            int(stride),
            int(red_delta),
            int(green_delta),
        )

    def filter_pixels(self, mode: c.ImageFilter, value: float | None = None) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("cpu_fallbacks")
        _renderer(self)._count("pixel_uploads")
        _renderer(self)._call(
            "pixel filter", _renderer(self)._require_canvas().filter_pixels, mode.value, value
        )

    def blend_region(
        self,
        source_image: object | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: c.BlendMode,
    ) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("cpu_fallbacks")
        _renderer(self)._count("pixel_uploads")
        if isinstance(source_image, Image):
            self._blend_image(
                source_image.to_rgba_bytes(),
                source_image.width,
                source_image.height,
                source,
                destination,
                mode,
            )
            return
        if source_image is None:
            self._blend_image(None, None, None, source, destination, mode)
            return
        convert = getattr(source_image, "convert", None)
        if callable(convert):
            source_image = convert("RGBA")
        width = getattr(source_image, "width", None)
        height = getattr(source_image, "height", None)
        tobytes = getattr(source_image, "tobytes", None)
        if not isinstance(width, int) or not isinstance(height, int) or not callable(tobytes):
            raise ArgumentValidationError("blend_region() source image must expose RGBA pixels.")
        raw_payload = tobytes()
        if isinstance(raw_payload, bytes):
            payload = raw_payload
        elif isinstance(raw_payload, bytearray):
            payload = bytes(raw_payload)
        elif isinstance(raw_payload, memoryview):
            payload = raw_payload.tobytes()
        else:
            raise ArgumentValidationError("blend_region() source image must expose RGBA bytes.")
        self._blend_image(payload, width, height, source, destination, mode)

    def save(self, path: str | Path) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._call("canvas export", _renderer(self)._require_canvas().save, str(path))

    def _pixel_payload(self, pixels: Sequence[int] | Buffer) -> bytes | Buffer:
        if isinstance(pixels, bytes | bytearray | memoryview | PixelBuffer):
            return pixels
        try:
            _renderer(self)._count("pixel_payload_copies")
            return bytes(pixels)
        except ValueError as exc:
            raise ArgumentValidationError(
                "Pixel values must be integers between 0 and 255."
            ) from exc

    def _upload_dirty_pixel_range(self, pixels: PixelBuffer) -> bool:
        dirty = pixels.dirty_range()
        if dirty is None or _renderer(self).physical_width <= 0:
            return False
        start, end = dirty
        if start % 4 != 0 or end % 4 != 0 or end <= start:
            return False
        pixel_start = start // 4
        pixel_end = end // 4
        if pixel_end <= pixel_start:
            return False
        canvas_width = int(_renderer(self).physical_width)
        row_start, col_start = divmod(pixel_start, canvas_width)
        row_end, last_col = divmod(pixel_end - 1, canvas_width)
        col_end = last_col + 1
        if row_start == row_end:
            width = col_end - col_start
            height = 1
        elif col_start == 0 and col_end == canvas_width:
            width = canvas_width
            height = row_end - row_start + 1
        else:
            return False
        _renderer(self)._count("pixel_uploads")
        callback = getattr(_renderer(self)._require_canvas(), "update_pixel_region_buffer", None)
        if not callable(callback):
            return False
        _renderer(self)._call(
            "dirty pixel region upload",
            callback,
            memoryview(pixels)[start:end],
            width,
            height,
            col_start,
            row_start,
            False,
        )
        return True

    def _blend_image(
        self,
        pixels: bytes | None,
        width: int | None,
        height: int | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: c.BlendMode,
    ) -> None:
        _renderer(self)._call(
            "region blending",
            _renderer(self)._require_canvas().blend_region,
            pixels,
            width,
            height,
            source,
            destination,
            mode,
        )
