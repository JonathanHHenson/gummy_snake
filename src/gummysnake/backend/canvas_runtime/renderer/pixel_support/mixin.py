"""Pixel and export operations for the Rust canvas renderer."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import cast

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.backend.canvas_runtime.renderer._protocols import _renderer
from gummysnake.backend.canvas_runtime.renderer.command_ingress import (
    pack_adjust_prefix_effect,
    pack_filter_effect,
)
from gummysnake.backend.canvas_runtime.renderer.pixel_support.uploads import (
    blend_image as _blend_image_impl,
)
from gummysnake.backend.canvas_runtime.renderer.pixel_support.uploads import (
    pixel_payload as _pixel_payload_impl,
)
from gummysnake.backend.canvas_runtime.renderer.pixel_support.uploads import (
    upload_dirty_pixel_range as _upload_dirty_pixel_range_impl,
)
from gummysnake.core.pixels import PixelBuffer
from gummysnake.exceptions import ArgumentValidationError


class CanvasRendererPixelsMixin:
    _last_pixel_bytes: bytes | None

    def load_pixels(self) -> PixelBuffer:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("pixel_readbacks")
        pixels = _renderer(self)._call(
            "pixel byte readback", _renderer(self)._require_canvas().load_pixel_bytes
        )
        return PixelBuffer(pixels)

    def load_pixel_bytes(self) -> bytes:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("pixel_readbacks")
        pixels = _renderer(self)._call(
            "pixel byte readback", _renderer(self)._require_canvas().load_pixel_bytes
        )
        if isinstance(pixels, bytes):
            self._last_pixel_bytes = pixels
            return pixels
        pixel_bytes = bytes(cast(Buffer | Sequence[int], pixels))
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
        if payload is pixels:
            _renderer(self)._call(
                "pixel buffer upload",
                _renderer(self)._require_canvas().update_pixel_buffer,
                payload,
            )
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
        _renderer(self)._call(
            "pixel write",
            _renderer(self)._require_canvas().set_pixel_rgba,
            int(x),
            int(y),
            tuple(max(0, min(255, int(channel))) for channel in rgba),
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
        if payload is pixels:
            _renderer(self)._call(
                "pixel region buffer upload",
                _renderer(self)._require_canvas().update_pixel_region_buffer,
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
        _renderer(self)._count("gpu_region_effect_passes")
        _renderer(self)._call(
            "typed pixel prefix adjustment",
            _renderer(self)._require_canvas_method(
                "apply_effects_packed",
                "typed pixel effect recording",
            ),
            pack_adjust_prefix_effect(byte_limit, stride, red_delta, green_delta),
        )

    def filter_pixels(self, mode: c.ImageFilter, value: float | None = None) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_region_effect_passes")
        _renderer(self)._call(
            "typed pixel filter",
            _renderer(self)._require_canvas_method(
                "apply_effects_packed",
                "typed pixel effect recording",
            ),
            pack_filter_effect(mode, value),
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
        return _pixel_payload_impl(_renderer(self), pixels)

    def _upload_dirty_pixel_range(self, pixels: PixelBuffer) -> bool:
        return _upload_dirty_pixel_range_impl(_renderer(self), pixels)

    def _blend_image(
        self,
        pixels: bytes | None,
        width: int | None,
        height: int | None,
        source: tuple[int, int, int, int],
        destination: tuple[int, int, int, int],
        mode: c.BlendMode,
    ) -> None:
        _blend_image_impl(_renderer(self), pixels, width, height, source, destination, mode)
