"""Compatibility imports for primitive path and clip support."""

from gummysnake.backend.canvas_runtime.renderer.primitive_support.paths import (
    CapturedShapeState,
    begin_clip,
    begin_clip_captured_shape,
    captured_point,
    complex_polygon,
    draw_captured_shape,
    end_clip,
    polygon,
)

__all__ = [
    "CapturedShapeState",
    "begin_clip",
    "begin_clip_captured_shape",
    "captured_point",
    "complex_polygon",
    "draw_captured_shape",
    "end_clip",
    "polygon",
]
