"""Compatibility imports for primitive batch support."""

from gummysnake.backend.canvas_runtime.renderer.primitive_support.batches import (
    _PRIMITIVE_ELLIPSE,
    _PRIMITIVE_LINE,
    _PRIMITIVE_RECT,
    _PRIMITIVE_TRIANGLE,
    flush_batches_before_primitive_batch,
    flush_line_batch,
    flush_line_batch_only,
    flush_primitive_batch_only,
    queue_fill_primitive_fast_path,
    queue_primitive_batch,
)

__all__ = [
    "_PRIMITIVE_ELLIPSE",
    "_PRIMITIVE_LINE",
    "_PRIMITIVE_RECT",
    "_PRIMITIVE_TRIANGLE",
    "flush_batches_before_primitive_batch",
    "flush_line_batch",
    "flush_line_batch_only",
    "flush_primitive_batch_only",
    "queue_fill_primitive_fast_path",
    "queue_primitive_batch",
]
