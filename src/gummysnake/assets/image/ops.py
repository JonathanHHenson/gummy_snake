"""Bulk image operations delegated to the canvas runtime."""

from __future__ import annotations

from typing import Any

from gummysnake import constants as c
from gummysnake.exceptions import ArgumentValidationError


def canvas_module() -> Any:
    """Canvas module using the active image context.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `Any`.
    """
    from gummysnake.rust.canvas import require_canvas_runtime

    return require_canvas_runtime()


def resize_rgba(
    source_width: int,
    source_height: int,
    source_pixels: bytes,
    target_width: int,
    target_height: int,
) -> bytearray:
    """Resize rgba using the active image context.
    
    Args:
        source_width: The source width value. Expected type: `int`.
        source_height: The source height value. Expected type: `int`.
        source_pixels: The source pixels value. Expected type: `bytes`.
        target_width: The target width value. Expected type: `int`.
        target_height: The target height value. Expected type: `int`.
    
    Returns:
        The return value. Type: `bytearray`.
    """
    return bytearray(
        canvas_module().image_resize_rgba(
            source_width,
            source_height,
            source_pixels,
            target_width,
            target_height,
        )
    )


def mask_rgba(
    width: int,
    height: int,
    pixels: bytes,
    mask_width: int,
    mask_height: int,
    mask_pixels: bytes,
) -> bytearray:
    """Mask rgba using the active image context.
    
    Args:
        width: The width value. Expected type: `int`.
        height: The height value. Expected type: `int`.
        pixels: The pixels value. Expected type: `bytes`.
        mask_width: The mask width value. Expected type: `int`.
        mask_height: The mask height value. Expected type: `int`.
        mask_pixels: The mask pixels value. Expected type: `bytes`.
    
    Returns:
        The return value. Type: `bytearray`.
    """
    return bytearray(
        canvas_module().image_mask_rgba(
            width,
            height,
            pixels,
            mask_width,
            mask_height,
            mask_pixels,
        )
    )


def filter_rgba(
    width: int,
    height: int,
    pixels: bytes,
    mode: c.ImageFilter,
    value: float | None,
) -> bytearray:
    """Filter rgba using the active image context.
    
    Args:
        width: The width value. Expected type: `int`.
        height: The height value. Expected type: `int`.
        pixels: The pixels value. Expected type: `bytes`.
        mode: The mode value. Expected type: `c.ImageFilter`.
        value: The value value. Expected type: `float | None`.
    
    Returns:
        The return value. Type: `bytearray`.
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
    return bytearray(canvas_module().image_filter_rgba(width, height, pixels, normalized, value))


def crop_rgba(width: int, height: int, pixels: bytes, sx: int, sy: int, sw: int, sh: int) -> bytes:
    """Crop rgba using the active image context.
    
    Args:
        width: The width value. Expected type: `int`.
        height: The height value. Expected type: `int`.
        pixels: The pixels value. Expected type: `bytes`.
        sx: The sx value. Expected type: `int`.
        sy: The sy value. Expected type: `int`.
        sw: The sw value. Expected type: `int`.
        sh: The sh value. Expected type: `int`.
    
    Returns:
        The return value. Type: `bytes`.
    """
    target_width = max(0, sw)
    target_height = max(0, sh)
    if target_width == 0 or target_height == 0:
        raise ArgumentValidationError("Image region dimensions must be positive.")
    return bytes(
        canvas_module().image_crop_rgba(
            width,
            height,
            pixels,
            sx,
            sy,
            target_width,
            target_height,
        )
    )


def alpha_composite_rgba(
    width: int,
    height: int,
    pixels: bytes,
    source_width: int,
    source_height: int,
    source_pixels: bytes,
    dx: int,
    dy: int,
) -> bytearray:
    """Alpha composite rgba using the active image context.
    
    Args:
        width: The width value. Expected type: `int`.
        height: The height value. Expected type: `int`.
        pixels: The pixels value. Expected type: `bytes`.
        source_width: The source width value. Expected type: `int`.
        source_height: The source height value. Expected type: `int`.
        source_pixels: The source pixels value. Expected type: `bytes`.
        dx: The dx value. Expected type: `int`.
        dy: The dy value. Expected type: `int`.
    
    Returns:
        The return value. Type: `bytearray`.
    """
    return bytearray(
        canvas_module().image_alpha_composite_rgba(
            width,
            height,
            pixels,
            source_width,
            source_height,
            source_pixels,
            dx,
            dy,
        )
    )


__all__ = [
    "alpha_composite_rgba",
    "canvas_module",
    "crop_rgba",
    "filter_rgba",
    "mask_rgba",
    "resize_rgba",
]
