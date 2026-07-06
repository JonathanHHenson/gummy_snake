"""Pixel payload and upload helpers for the Rust canvas renderer."""

from __future__ import annotations

from collections.abc import Buffer, Sequence

from gummysnake import constants as c
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.core.pixels import PixelBuffer, dirty_pixel_region
from gummysnake.exceptions import ArgumentValidationError


def pixel_payload(self: CanvasRendererHost, pixels: Sequence[int] | Buffer) -> bytes | Buffer:
    if isinstance(pixels, bytes | bytearray | memoryview | PixelBuffer):
        return pixels
    try:
        self._count("pixel_payload_copies")
        return bytes(pixels)
    except ValueError as exc:
        raise ArgumentValidationError("Pixel values must be integers between 0 and 255.") from exc


def upload_dirty_pixel_range(self: CanvasRendererHost, pixels: PixelBuffer) -> bool:
    dirty = pixels.dirty_range()
    if dirty is None:
        return False
    region = dirty_pixel_region(
        len(pixels),
        int(self.physical_width),
        int(self.physical_height),
        dirty,
    )
    if not region.valid:
        return False
    if region.empty:
        return True
    callback = getattr(self._require_canvas(), "update_pixel_region_buffer", None)
    if not callable(callback):
        return False
    self._count("pixel_uploads")
    self._call(
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


def blend_image(
    self: CanvasRendererHost,
    pixels: bytes | None,
    width: int | None,
    height: int | None,
    source: tuple[int, int, int, int],
    destination: tuple[int, int, int, int],
    mode: c.BlendMode,
) -> None:
    self._call(
        "region blending",
        self._require_canvas().blend_region,
        pixels,
        width,
        height,
        source,
        destination,
        mode,
    )
