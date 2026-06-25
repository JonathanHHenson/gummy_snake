"""Pixel and export operations for the Rust canvas renderer."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import cast

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.backend._canvas.renderer._protocols import CanvasRendererHost
from gummysnake.exceptions import ArgumentValidationError
from gummysnake.pixels import PixelBuffer
from gummysnake.pixels._buffer import dirty_pixel_region


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


class CanvasRendererPixelsMixin:
    _last_pixel_bytes: bytes | None

    def load_pixels(self) -> PixelBuffer:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("pixel_readbacks")
        callback = getattr(_renderer(self)._require_canvas(), "load_pixel_bytes", None)
        if callable(callback):
            pixels = _renderer(self)._call("pixel byte readback", callback)
        else:
            pixels = _renderer(self)._call(
                "pixel readback", _renderer(self)._require_canvas().load_pixels
            )
        return PixelBuffer(pixels)

    def load_pixel_bytes(self) -> bytes:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("pixel_readbacks")
        callback = getattr(_renderer(self)._require_canvas(), "load_pixel_bytes", None)
        if callable(callback):
            pixels = _renderer(self)._call("pixel byte readback", callback)
            if isinstance(pixels, bytes):
                self._last_pixel_bytes = pixels
                return pixels
            pixel_bytes = bytes(cast(Buffer | Sequence[int], pixels))
            self._last_pixel_bytes = pixel_bytes
            return pixel_bytes
        pixels = cast(
            Buffer | Sequence[int],
            _renderer(self)._call("pixel readback", _renderer(self)._require_canvas().load_pixels),
        )
        pixel_bytes = bytes(pixels)
        self._last_pixel_bytes = pixel_bytes
        return pixel_bytes

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
        last_pixel_bytes = getattr(self, "_last_pixel_bytes", None)
        if pixels is last_pixel_bytes or (
            isinstance(pixels, memoryview)
            and isinstance(pixels.obj, bytes)
            and pixels.obj is last_pixel_bytes
        ):
            _renderer(self)._count("pixel_noop_upload_skips")
            return
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

    def save_gif(self, path: str | Path, count: int, frame_duration_ms: int) -> None:
        _renderer(self)._flush_line_batch()
        callback = _renderer(self)._require_canvas_method("save_gif", "GIF export")
        _renderer(self)._call(
            "GIF export",
            callback,
            str(path),
            int(count),
            int(frame_duration_ms),
        )

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
        if dirty is None:
            return False
        renderer = _renderer(self)
        region = dirty_pixel_region(
            len(pixels),
            int(renderer.physical_width),
            int(renderer.physical_height),
            dirty,
        )
        if not region.valid:
            return False
        if region.empty:
            return True
        callback = getattr(renderer._require_canvas(), "update_pixel_region_buffer", None)
        if not callable(callback):
            return False
        renderer._count("pixel_uploads")
        renderer._call(
            "dirty pixel region upload",
            callback,
            memoryview(pixels)[region.byte_slice],
            region.width,
            region.height,
            region.x,
            region.y,
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
