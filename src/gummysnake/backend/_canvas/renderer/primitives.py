"""Primitive drawing methods for the Rust canvas renderer."""

from __future__ import annotations

from typing import Any, cast

from gummysnake import constants as c
from gummysnake.backend._canvas.renderer._protocols import CanvasRendererHost
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D

_PRIMITIVE_RECT = 1
_PRIMITIVE_TRIANGLE = 2
_PRIMITIVE_ELLIPSE = 3
_PRIMITIVE_LINE = 4


def _renderer(self: object) -> CanvasRendererHost:
    return cast(CanvasRendererHost, self)


class CanvasRendererPrimitivesMixin:
    def background(self, color: Color) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call(
            "background drawing", _renderer(self)._require_canvas().background, color.to_tuple()
        )

    def clear(self) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        _renderer(self)._call("canvas clearing", _renderer(self)._require_canvas().clear)

    def point(self, x: float, y: float, style: StyleState, transform: Matrix2D) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        current = (
            getattr(_renderer(self)._require_canvas(), "point_current", None)
            if _renderer(self)._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            _renderer(self)._call("point drawing", current, x, y)
            return
        _renderer(self)._call(
            "point drawing",
            _renderer(self)._require_canvas().point,
            x,
            y,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        if self._queue_primitive_batch(
            _PRIMITIVE_LINE,
            (x1, y1, x2, y2, 0.0, 0.0),
            style,
            transform,
        ):
            return
        renderer = _renderer(self)
        renderer._flush_image_batch()
        batch_lines_current = (
            getattr(renderer._require_canvas(), "batch_lines_current", None)
            if renderer._can_use_current_state(style, transform)
            else None
        )
        line_batch = renderer._line_batch_state
        if callable(batch_lines_current):
            if line_batch.has_records() and not line_batch.matches_current():
                renderer._flush_line_batch()
            line_batch.append_current((x1, y1, x2, y2))
            return
        style_payload = renderer._style_payload(style)
        matrix_payload = renderer._matrix_payload(transform)
        if line_batch.has_records() and not line_batch.matches_style(style_payload, matrix_payload):
            renderer._flush_line_batch()
        renderer._line_batch_state.append_styled((x1, y1, x2, y2), style_payload, matrix_payload)

    def polygon(
        self,
        points: list[tuple[float, float]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        current = (
            getattr(_renderer(self)._require_canvas(), "polygon_current", None)
            if _renderer(self)._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            _renderer(self)._call("polygon drawing", current, points, close)
            return
        _renderer(self)._call(
            "polygon drawing",
            _renderer(self)._require_canvas().polygon,
            points,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
            close,
        )

    def complex_polygon(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        style: StyleState,
        transform: Matrix2D,
        *,
        close: bool = True,
    ) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        current = (
            getattr(_renderer(self)._require_canvas(), "complex_polygon_current", None)
            if _renderer(self)._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            _renderer(self)._call("complex polygon drawing", current, outer, contours, close)
            return
        _renderer(self)._call(
            "complex polygon drawing",
            _renderer(self)._require_canvas_method("complex_polygon", "contour drawing"),
            outer,
            contours,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
            close,
        )

    def draw_captured_shape(
        self, state: object, style: StyleState, transform: Matrix2D, *, close: bool = True
    ) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        draw = (
            getattr(_renderer(self)._require_canvas(), "draw_captured_shape_current", None)
            if _renderer(self)._can_use_current_state(style, transform)
            else None
        )
        if callable(draw):
            _renderer(self)._count("direct_shape_finalizations")
            _renderer(self)._call("captured shape drawing", draw, state, close)
            return
        draw_explicit = getattr(_renderer(self)._require_canvas(), "draw_captured_shape", None)
        if callable(draw_explicit):
            _renderer(self)._count("direct_shape_finalizations")
            _renderer(self)._call(
                "captured shape drawing",
                draw_explicit,
                state,
                _renderer(self)._style_payload(style),
                _renderer(self)._matrix_payload(transform),
                close,
            )
            return
        _renderer(self)._count("shape_buffer_extractions")
        state_obj = cast(Any, state)
        outer = [tuple(point) for point in state_obj.shape_vertices()]
        contours = [list(contour) for contour in state_obj.shape_contours()]
        if contours:
            self.complex_polygon(
                outer,
                contours,
                style,
                transform,
                close=close,
            )
        else:
            self.polygon(outer, style, transform, close=close)
        reset = getattr(state_obj, "reset_shape_capture", None)
        if callable(reset):
            reset()

    def begin_clip(
        self,
        outer: list[tuple[float, float]],
        contours: list[list[tuple[float, float]]],
        transform: Matrix2D,
    ) -> None:
        _renderer(self)._flush_line_batch()
        current = (
            getattr(_renderer(self)._require_canvas(), "begin_clip_current", None)
            if getattr(_renderer(self), "_rust_transform_synced", True)
            and (
                _renderer(self)._current_matrix_payload
                == _renderer(self)._matrix_payload(transform)
            )
            else None
        )
        if callable(current):
            _renderer(self)._call("clip creation", current, outer, contours)
            _renderer(self)._clip_depth += 1
            return
        _renderer(self)._call(
            "clip creation",
            _renderer(self)._require_canvas_method("begin_clip", "path clipping"),
            outer,
            contours,
            _renderer(self)._matrix_payload(transform),
        )
        _renderer(self)._clip_depth += 1

    def begin_clip_captured_shape(self, state: object, transform: Matrix2D) -> None:
        _renderer(self)._flush_line_batch()
        current = (
            getattr(_renderer(self)._require_canvas(), "begin_clip_captured_current", None)
            if getattr(_renderer(self), "_rust_transform_synced", True)
            and (
                _renderer(self)._current_matrix_payload
                == _renderer(self)._matrix_payload(transform)
            )
            else None
        )
        if callable(current):
            _renderer(self)._count("direct_shape_finalizations")
            _renderer(self)._call("captured clip creation", current, state)
            _renderer(self)._clip_depth += 1
            return
        begin_explicit = getattr(_renderer(self)._require_canvas(), "begin_clip_captured", None)
        if callable(begin_explicit):
            _renderer(self)._count("direct_shape_finalizations")
            _renderer(self)._call(
                "captured clip creation",
                begin_explicit,
                state,
                _renderer(self)._matrix_payload(transform),
            )
            _renderer(self)._clip_depth += 1
            return
        _renderer(self)._count("shape_buffer_extractions")
        state_obj = cast(Any, state)
        self.begin_clip(
            [tuple(point) for point in state_obj.shape_vertices()],
            [list(contour) for contour in state_obj.shape_contours()],
            transform,
        )
        reset = getattr(state_obj, "reset_shape_capture", None)
        if callable(reset):
            reset()

    def end_clip(self) -> None:
        _renderer(self)._flush_line_batch()
        if _renderer(self)._clip_depth <= 0:
            from gummysnake.exceptions import ArgumentValidationError

            raise ArgumentValidationError("end_clip() called without matching begin_clip().")
        _renderer(self)._call(
            "clip restoration",
            _renderer(self)._require_canvas_method("end_clip", "path clipping"),
        )
        _renderer(self)._clip_depth -= 1

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        if self._queue_primitive_batch(
            _PRIMITIVE_RECT,
            (x, y, width, height, 0.0, 0.0),
            style,
            transform,
        ):
            return
        _renderer(self)._flush_line_batch()
        current = (
            getattr(_renderer(self)._require_canvas(), "rect_current", None)
            if _renderer(self)._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            _renderer(self)._count("gpu_draws")
            _renderer(self)._call("rectangle drawing", current, x, y, width, height)
            return
        callback = getattr(_renderer(self)._require_canvas(), "rect", None)
        if callable(callback):
            _renderer(self)._count("gpu_draws")
            _renderer(self)._call(
                "rectangle drawing",
                callback,
                x,
                y,
                width,
                height,
                _renderer(self)._style_payload(style),
                _renderer(self)._matrix_payload(transform),
            )
            return
        self.polygon(
            [(x, y), (x + width, y), (x + width, y + height), (x, y + height)], style, transform
        )

    def triangle(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        if self._queue_primitive_batch(
            _PRIMITIVE_TRIANGLE,
            (x1, y1, x2, y2, x3, y3),
            style,
            transform,
        ):
            return
        _renderer(self)._flush_line_batch()
        current = (
            getattr(_renderer(self)._require_canvas(), "triangle_current", None)
            if _renderer(self)._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            _renderer(self)._count("gpu_draws")
            _renderer(self)._call("triangle drawing", current, x1, y1, x2, y2, x3, y3)
            return
        callback = getattr(_renderer(self)._require_canvas(), "triangle", None)
        if callable(callback):
            _renderer(self)._count("gpu_draws")
            _renderer(self)._call(
                "triangle drawing",
                callback,
                x1,
                y1,
                x2,
                y2,
                x3,
                y3,
                _renderer(self)._style_payload(style),
                _renderer(self)._matrix_payload(transform),
            )
            return
        self.polygon([(x1, y1), (x2, y2), (x3, y3)], style, transform, close=True)

    def quad(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        x4: float,
        y4: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        _renderer(self)._flush_line_batch()
        current = (
            getattr(_renderer(self)._require_canvas(), "quad_current", None)
            if _renderer(self)._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            _renderer(self)._count("gpu_draws")
            _renderer(self)._call("quadrilateral drawing", current, x1, y1, x2, y2, x3, y3, x4, y4)
            return
        callback = getattr(_renderer(self)._require_canvas(), "quad", None)
        if callable(callback):
            _renderer(self)._count("gpu_draws")
            _renderer(self)._call(
                "quadrilateral drawing",
                callback,
                x1,
                y1,
                x2,
                y2,
                x3,
                y3,
                x4,
                y4,
                _renderer(self)._style_payload(style),
                _renderer(self)._matrix_payload(transform),
            )
            return
        self.polygon([(x1, y1), (x2, y2), (x3, y3), (x4, y4)], style, transform, close=True)

    def ellipse(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        if self._queue_primitive_batch(
            _PRIMITIVE_ELLIPSE,
            (x, y, width, height, 0.0, 0.0),
            style,
            transform,
        ):
            return
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        current = (
            getattr(_renderer(self)._require_canvas(), "ellipse_current", None)
            if _renderer(self)._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            _renderer(self)._call("ellipse drawing", current, x, y, width, height)
            return
        _renderer(self)._call(
            "ellipse drawing",
            _renderer(self)._require_canvas().ellipse,
            x,
            y,
            width,
            height,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
        )

    def arc(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        start: float,
        stop: float,
        mode: c.ArcMode,
        style: StyleState,
        transform: Matrix2D,
    ) -> None:
        _renderer(self)._flush_line_batch()
        _renderer(self)._count("gpu_draws")
        current = (
            getattr(_renderer(self)._require_canvas(), "arc_current", None)
            if _renderer(self)._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            _renderer(self)._call("arc drawing", current, x, y, width, height, start, stop, mode)
            return
        _renderer(self)._call(
            "arc drawing",
            _renderer(self)._require_canvas().arc,
            x,
            y,
            width,
            height,
            start,
            stop,
            mode,
            _renderer(self)._style_payload(style),
            _renderer(self)._matrix_payload(transform),
        )

    def _flush_line_batch(self) -> None:
        _renderer(self)._flush_line_batch_only()
        _renderer(self)._flush_primitive_batch_only()
        _renderer(self)._flush_image_batch()
        _renderer(self)._flush_text_batch()

    def queue_fill_primitive_fast_path(
        self,
        kind: int,
        coords: tuple[float, ...],
        style: StyleState,
        transform: Matrix2D,
    ) -> bool:
        """Queue a fill-only primitive into the compact Rust batch when available."""

        renderer = _renderer(self)
        fill_color = style.fill_color
        canvas = getattr(renderer, "_canvas", None)
        batch_fill = getattr(canvas, "batch_fill_primitives", None) if canvas is not None else None
        if (
            kind == _PRIMITIVE_LINE
            or fill_color is None
            or style.stroke_color is not None
            or style.erasing
            or style.blend_mode != c.BLEND
            or not callable(batch_fill)
        ):
            return False

        matrix_payload = renderer._matrix_payload(transform)
        self._flush_batches_before_primitive_batch()
        primitive_batch = renderer._primitive_batch_state
        if primitive_batch.has_records() and not primitive_batch.matches_fill(matrix_payload):
            renderer._flush_primitive_batch_only()
        renderer._primitive_batch_state.append_fill(
            (kind, *coords, *fill_color.to_tuple()), matrix_payload
        )
        return True

    def _queue_primitive_batch(
        self,
        kind: int,
        coords: tuple[float, float, float, float, float, float],
        style: StyleState,
        transform: Matrix2D,
    ) -> bool:
        if self.queue_fill_primitive_fast_path(kind, coords, style, transform):
            return True

        renderer = _renderer(self)
        canvas = renderer._require_canvas()
        matrix_payload = renderer._matrix_payload(transform)
        batch_mixed = getattr(canvas, "batch_primitives_mixed", None)
        if callable(batch_mixed):
            self._flush_batches_before_primitive_batch()
            primitive_batch = renderer._primitive_batch_state
            if primitive_batch.has_records() and not primitive_batch.matches_mixed():
                renderer._flush_primitive_batch_only()
            renderer._primitive_batch_state.append_mixed(
                (kind, *coords, renderer._style_payload(style), matrix_payload)
            )
            return True

        current = (
            getattr(canvas, "batch_primitives_current", None)
            if renderer._can_use_current_state(style, transform)
            else None
        )
        if callable(current):
            self._flush_batches_before_primitive_batch()
            primitive_batch = renderer._primitive_batch_state
            if primitive_batch.has_records() and not primitive_batch.matches_current():
                renderer._flush_primitive_batch_only()
            renderer._primitive_batch_state.append_current((kind, *coords))
            return True

        batch = getattr(canvas, "batch_primitives", None)
        if not callable(batch):
            return False
        style_payload = renderer._style_payload(style)
        self._flush_batches_before_primitive_batch()
        primitive_batch = renderer._primitive_batch_state
        if primitive_batch.has_records() and not primitive_batch.matches_styled(
            style_payload,
            matrix_payload,
        ):
            renderer._flush_primitive_batch_only()
        renderer._primitive_batch_state.append_styled(
            (kind, *coords), style_payload, matrix_payload
        )
        return True

    def _flush_batches_before_primitive_batch(self) -> None:
        renderer = _renderer(self)
        if renderer._line_batch_state.has_records():
            renderer._flush_line_batch_only()
        if renderer._text_batch:
            renderer._flush_text_batch()
        renderer._flush_image_batch()

    def _flush_line_batch_only(self) -> None:
        renderer = _renderer(self)
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

    def _flush_primitive_batch_only(self) -> None:
        renderer = _renderer(self)
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
