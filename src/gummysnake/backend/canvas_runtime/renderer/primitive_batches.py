"""Primitive batch queuing and flushing helpers for the Rust canvas renderer."""

from __future__ import annotations

from gummysnake import constants as c
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
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


def flush_primitive_batch_only(self: CanvasRendererHost) -> None:
    renderer = self
    if not renderer._primitive_batch_state.has_records():
        return
    snapshot = renderer._primitive_batch_state.drain()
    records = snapshot.records
    style = snapshot.style
    matrix = snapshot.matrix
    current = snapshot.current
    mode = snapshot.mode
    canvas = renderer._require_canvas()
    if mode == "mixed":
        batch_mixed = getattr(canvas, "batch_primitives_mixed", None)
        if callable(batch_mixed):
            renderer._count("gpu_draws", len(records))
            renderer._count("primitive_batch_records", len(records))
            renderer._count("primitive_batch_flushes")
            renderer._max_count("primitive_batch_max_records", len(records))
            renderer._call("mixed batched primitive drawing", batch_mixed, records)
            return
    if mode == "fill" and matrix is not None:
        batch_fill = getattr(canvas, "batch_fill_primitives", None)
        if callable(batch_fill):
            renderer._count("gpu_draws", len(records))
            renderer._count("primitive_batch_records", len(records))
            renderer._count("primitive_batch_flushes")
            renderer._max_count("primitive_batch_max_records", len(records))
            renderer._call("batched fill primitive drawing", batch_fill, records, matrix)
            return
    if current:
        batch_current = getattr(canvas, "batch_primitives_current", None)
        if callable(batch_current):
            renderer._count("gpu_draws", len(records))
            renderer._count("primitive_batch_records", len(records))
            renderer._count("primitive_batch_flushes")
            renderer._max_count("primitive_batch_max_records", len(records))
            renderer._call("batched primitive drawing", batch_current, records)
            return
    elif style is not None and matrix is not None:
        batch = getattr(canvas, "batch_primitives", None)
        if callable(batch):
            renderer._count("gpu_draws", len(records))
            renderer._count("primitive_batch_records", len(records))
            renderer._count("primitive_batch_flushes")
            renderer._max_count("primitive_batch_max_records", len(records))
            renderer._call("batched primitive drawing", batch, records, style, matrix)
            return

    renderer._count("primitive_batch_fallbacks", len(records))
    for kind, a, b, c1, d, e, f in records:
        renderer._count("gpu_draws")
        if kind == _PRIMITIVE_RECT and style is not None and matrix is not None:
            renderer._call("rectangle drawing", canvas.rect, a, b, c1, d, style, matrix)
        elif kind == _PRIMITIVE_TRIANGLE and style is not None and matrix is not None:
            renderer._call(
                "triangle drawing",
                canvas.triangle,
                a,
                b,
                c1,
                d,
                e,
                f,
                style,
                matrix,
            )
        elif kind == _PRIMITIVE_ELLIPSE and style is not None and matrix is not None:
            renderer._call("ellipse drawing", canvas.ellipse, a, b, c1, d, style, matrix)
        elif kind == _PRIMITIVE_LINE and style is not None and matrix is not None:
            renderer._call("line drawing", canvas.line, a, b, c1, d, style, matrix)
