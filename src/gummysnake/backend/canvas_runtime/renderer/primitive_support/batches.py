"""Primitive batch queuing and flushing helpers for the Rust canvas renderer."""

from __future__ import annotations

from collections.abc import Callable

from gummysnake import constants as c
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.backend.canvas_runtime.renderer.renderer_state.batch_state import (
    PrimitiveBatchSnapshot,
)
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D

_PRIMITIVE_RECT = 1
_PRIMITIVE_TRIANGLE = 2
_PRIMITIVE_ELLIPSE = 3
_PRIMITIVE_LINE = 4


def flush_line_batch(self: CanvasRendererHost) -> None:
    self._flush_line_batch_only()
    self._flush_primitive_batch_only()
    self._flush_image_batch()
    self._flush_model_batch()
    self._flush_text_batch()


def queue_fill_primitive_fast_path(
    self: CanvasRendererHost,
    kind: int,
    coords: tuple[float, ...],
    style: StyleState,
    transform: Matrix2D,
) -> bool:
    fill_color = style.fill_rgba
    canvas = getattr(self, "_canvas", None)
    batch_fill = getattr(canvas, "batch_fill_primitives", None) if canvas is not None else None
    if (
        kind == _PRIMITIVE_LINE
        or fill_color is None
        or style.stroke_rgba is not None
        or style.erasing
        or style.blend_mode != c.BLEND
        or not callable(batch_fill)
    ):
        return False

    matrix_payload = self._matrix_payload(transform)
    flush_batches_before_primitive_batch(self)
    primitive_batch = self._primitive_batch_state
    if primitive_batch.has_records() and not primitive_batch.matches_fill(matrix_payload):
        self._flush_primitive_batch_only()
    self._primitive_batch_state.append_fill((kind, *coords, *fill_color), matrix_payload)
    return True


def queue_primitive_batch(
    self: CanvasRendererHost,
    kind: int,
    coords: tuple[float, float, float, float, float, float],
    style: StyleState,
    transform: Matrix2D,
) -> bool:
    if queue_fill_primitive_fast_path(self, kind, coords, style, transform):
        return True

    canvas = self._require_canvas()
    matrix_payload = self._matrix_payload(transform)
    batch_mixed = getattr(canvas, "batch_primitives_mixed", None)
    if callable(batch_mixed):
        flush_batches_before_primitive_batch(self)
        primitive_batch = self._primitive_batch_state
        if primitive_batch.has_records() and not primitive_batch.matches_mixed():
            self._flush_primitive_batch_only()
        self._primitive_batch_state.append_mixed(
            (kind, *coords, self._style_payload(style), matrix_payload)
        )
        return True

    current = (
        getattr(canvas, "batch_primitives_current", None)
        if self._can_use_current_state(style, transform)
        else None
    )
    if callable(current):
        flush_batches_before_primitive_batch(self)
        primitive_batch = self._primitive_batch_state
        if primitive_batch.has_records() and not primitive_batch.matches_current():
            self._flush_primitive_batch_only()
        self._primitive_batch_state.append_current((kind, *coords))
        return True

    batch = getattr(canvas, "batch_primitives", None)
    if not callable(batch):
        return False
    style_payload = self._style_payload(style)
    flush_batches_before_primitive_batch(self)
    primitive_batch = self._primitive_batch_state
    if primitive_batch.has_records() and not primitive_batch.matches_styled(
        style_payload,
        matrix_payload,
    ):
        self._flush_primitive_batch_only()
    self._primitive_batch_state.append_styled((kind, *coords), style_payload, matrix_payload)
    return True


def flush_batches_before_primitive_batch(self: CanvasRendererHost) -> None:
    if self._line_batch_state.has_records():
        self._flush_line_batch_only()
    if self._text_batch:
        self._flush_text_batch()
    self._flush_image_batch()
    self._flush_model_batch()


def flush_line_batch_only(self: CanvasRendererHost) -> None:
    renderer = self
    if not renderer._line_batch_state.has_records():
        return
    snapshot = renderer._line_batch_state.drain()
    lines = snapshot.records
    style = snapshot.style
    matrix = snapshot.matrix
    if snapshot.current:
        canvas = renderer._require_canvas()
        batch_lines_current = getattr(canvas, "batch_lines_current", None)
        if callable(batch_lines_current):
            renderer._count("gpu_draws", len(lines))
            renderer._call("batched line drawing", batch_lines_current, lines)
            return
        for x1, y1, x2, y2 in lines:
            line_current = getattr(canvas, "line_current", None)
            if callable(line_current):
                renderer._count("gpu_draws")
                renderer._call("line drawing", line_current, x1, y1, x2, y2)
        return
    if style is None or matrix is None:
        return
    canvas = renderer._require_canvas()
    batch_lines = getattr(canvas, "batch_lines", None)
    if callable(batch_lines):
        renderer._count("gpu_draws", len(lines))
        renderer._call("batched line drawing", batch_lines, lines, style, matrix)
        return
    for x1, y1, x2, y2 in lines:
        renderer._count("gpu_draws")
        renderer._call("line drawing", canvas.line, x1, y1, x2, y2, style, matrix)


def _drain_primitive_batch(renderer: CanvasRendererHost) -> PrimitiveBatchSnapshot:
    """Transfer the pending batch state into one immutable flush snapshot."""
    return renderer._primitive_batch_state.drain()


def _native_primitive_batch_submission(
    renderer: CanvasRendererHost,
    snapshot: PrimitiveBatchSnapshot,
) -> tuple[str, Callable[..., object], tuple[object, ...]] | None:
    """Select the native call and payload tuple for an already-drained batch."""
    canvas = renderer._require_canvas()
    records = snapshot.records
    if snapshot.mode == "mixed":
        callback = getattr(canvas, "batch_primitives_mixed", None)
        if callable(callback):
            return "mixed batched primitive drawing", callback, (records,)
    if snapshot.mode == "fill" and snapshot.matrix is not None:
        callback = getattr(canvas, "batch_fill_primitives", None)
        if callable(callback):
            return "batched fill primitive drawing", callback, (records, snapshot.matrix)
    if snapshot.current:
        callback = getattr(canvas, "batch_primitives_current", None)
        if callable(callback):
            return "batched primitive drawing", callback, (records,)
    if snapshot.style is not None and snapshot.matrix is not None:
        callback = getattr(canvas, "batch_primitives", None)
        if callable(callback):
            return "batched primitive drawing", callback, (records, snapshot.style, snapshot.matrix)
    return None


def _record_primitive_batch_submission(
    renderer: CanvasRendererHost,
    record_count: int,
) -> None:
    """Update batch diagnostics exactly once for a native batch submission."""
    renderer._count("gpu_draws", record_count)
    renderer._count("primitive_batch_records", record_count)
    renderer._count("primitive_batch_flushes")
    renderer._max_count("primitive_batch_max_records", record_count)


def _submit_native_primitive_batch(
    renderer: CanvasRendererHost,
    snapshot: PrimitiveBatchSnapshot,
) -> bool:
    """Submit one compatible native primitive batch and record its diagnostics."""
    submission = _native_primitive_batch_submission(renderer, snapshot)
    if submission is None:
        return False
    operation, callback, payload = submission
    _record_primitive_batch_submission(renderer, len(snapshot.records))
    renderer._call(operation, callback, *payload)
    return True


def _submit_unbatched_primitive_records(
    renderer: CanvasRendererHost,
    snapshot: PrimitiveBatchSnapshot,
) -> None:
    """Preserve the legacy per-primitive bridge path when native batching is absent."""
    canvas = renderer._require_canvas()
    renderer._count("primitive_batch_fallbacks", len(snapshot.records))
    for kind, a, b, c1, d, e, f in snapshot.records:
        renderer._count("gpu_draws")
        if kind == _PRIMITIVE_RECT and snapshot.style is not None and snapshot.matrix is not None:
            renderer._call(
                "rectangle drawing", canvas.rect, a, b, c1, d, snapshot.style, snapshot.matrix
            )
        elif (
            kind == _PRIMITIVE_TRIANGLE
            and snapshot.style is not None
            and snapshot.matrix is not None
        ):
            renderer._call(
                "triangle drawing",
                canvas.triangle,
                a,
                b,
                c1,
                d,
                e,
                f,
                snapshot.style,
                snapshot.matrix,
            )
        elif (
            kind == _PRIMITIVE_ELLIPSE
            and snapshot.style is not None
            and snapshot.matrix is not None
        ):
            renderer._call(
                "ellipse drawing", canvas.ellipse, a, b, c1, d, snapshot.style, snapshot.matrix
            )
        elif kind == _PRIMITIVE_LINE and snapshot.style is not None and snapshot.matrix is not None:
            renderer._call(
                "line drawing", canvas.line, a, b, c1, d, snapshot.style, snapshot.matrix
            )


def flush_primitive_batch_only(self: CanvasRendererHost) -> None:
    """Flush pending primitives without crossing an ordered command-family boundary."""
    renderer = self
    if not renderer._primitive_batch_state.has_records():
        return
    snapshot = _drain_primitive_batch(renderer)
    if _submit_native_primitive_batch(renderer, snapshot):
        return
    _submit_unbatched_primitive_records(renderer, snapshot)
