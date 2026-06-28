"""Pixel payload and upload helpers for the Rust canvas renderer."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from typing import cast

from gummysnake import constants as c
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.core.pixels import PixelBuffer, dirty_pixel_region
from gummysnake.exceptions import ArgumentValidationError


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


def pixel_payload(self: object, pixels: Sequence[int] | Buffer) -> bytes | Buffer:
    """Pixel payload.
    
    Args:
        pixels: The pixels value. Expected type: `Sequence[int] | Buffer`.
    
    Returns:
        The return value. Type: `bytes | Buffer`.
    """
    if isinstance(pixels, bytes | bytearray | memoryview | PixelBuffer):
        return pixels
    try:
        _renderer(self)._count("pixel_payload_copies")
        return bytes(pixels)
    except ValueError as exc:
        raise ArgumentValidationError("Pixel values must be integers between 0 and 255.") from exc


def upload_dirty_pixel_range(self: object, pixels: PixelBuffer) -> bool:
    """Upload dirty pixel range.
    
    Args:
        pixels: The pixels value. Expected type: `PixelBuffer`.
    
    Returns:
        The return value. Type: `bool`.
    """
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


def blend_image(
    self: object,
    pixels: bytes | None,
    width: int | None,
    height: int | None,
    source: tuple[int, int, int, int],
    destination: tuple[int, int, int, int],
    mode: c.BlendMode,
) -> None:
    """Blend image.
    
    Args:
        pixels: The pixels value. Expected type: `bytes | None`.
        width: The width value. Expected type: `int | None`.
        height: The height value. Expected type: `int | None`.
        source: The source value. Expected type: `tuple[int, int, int, int]`.
        destination: The destination value. Expected type: `tuple[int, int, int, int]`.
        mode: The mode value. Expected type: `c.BlendMode`.
    
    Returns:
        None.
    """
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
