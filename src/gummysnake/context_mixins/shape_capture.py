"""Compatibility imports for Rust-backed shape capture helpers."""

from gummysnake.context_mixins.shape_support.capture import (
    active_shape_vertices,
    begin_clip,
    begin_contour,
    begin_shape,
    bezier_vertex,
    clip,
    clip_path,
    contour,
    end_clip,
    end_contour,
    end_shape,
    quadratic_vertex,
    reset_shape_capture,
    shape,
    spline_vertex,
    vertex,
)

__all__ = [
    "active_shape_vertices",
    "begin_clip",
    "begin_contour",
    "begin_shape",
    "bezier_vertex",
    "clip",
    "clip_path",
    "contour",
    "end_clip",
    "end_contour",
    "end_shape",
    "quadratic_vertex",
    "reset_shape_capture",
    "shape",
    "spline_vertex",
    "vertex",
]
