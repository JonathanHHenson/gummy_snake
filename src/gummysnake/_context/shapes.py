"""2D primitive and curve drawing methods for SketchContext."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

from gummysnake import constants as c
from gummysnake._context._protocols import SketchContextHost
from gummysnake.core.geometry import (
    flatten_cubic,
    flatten_quadratic,
    flatten_spline,
    resolve_ellipse,
    resolve_rect,
)
from gummysnake.core.geometry import spline_point as geometry_spline_point
from gummysnake.core.geometry import spline_tangent as geometry_spline_tangent
from gummysnake.exceptions import ArgumentValidationError


class ShapeContextMixin:
    renderer: Any
    state: Any
    _spline_tightness: float

    def point(self, x: float, y: float) -> None:
        self.renderer.point(float(x), float(y), self.state.style, self.state.transform.matrix)

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.renderer.line(
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            self.state.style,
            self.state.transform.matrix,
        )

    def rect(self, x: float, y: float, width: float, height: float | None = None) -> None:
        h = width if height is None else height
        rx, ry, rw, rh = resolve_rect(
            self.state.style.rect_mode, float(x), float(y), float(width), float(h)
        )
        self.renderer.rect(rx, ry, rw, rh, self.state.style, self.state.transform.matrix)

    def square(self, x: float, y: float, size: float) -> None:
        self.rect(x, y, size, size)

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None:
        h = width if height is None else height
        ex, ey, ew, eh = resolve_ellipse(
            self.state.style.ellipse_mode, float(x), float(y), float(width), float(h)
        )
        self.renderer.ellipse(ex, ey, ew, eh, self.state.style, self.state.transform.matrix)

    def circle(self, x: float, y: float, diameter: float) -> None:
        self.ellipse(x, y, diameter, diameter)

    def triangle(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
        self.renderer.triangle(
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            float(x3),
            float(y3),
            self.state.style,
            self.state.transform.matrix,
        )

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
    ) -> None:
        self.renderer.quad(
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            float(x3),
            float(y3),
            float(x4),
            float(y4),
            self.state.style,
            self.state.transform.matrix,
        )

    def arc(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        start: float,
        stop: float,
        mode: c.ArcMode = c.OPEN,
    ) -> None:
        ex, ey, ew, eh = resolve_ellipse(
            self.state.style.ellipse_mode, float(x), float(y), float(width), float(height)
        )
        self.renderer.arc(
            ex,
            ey,
            ew,
            eh,
            cast(SketchContextHost, self)._angle(start),
            cast(SketchContextHost, self)._angle(stop),
            mode,
            self.state.style,
            self.state.transform.matrix,
        )

    def begin_shape(self, kind: c.ShapeKind | None = None) -> None:
        if self.state.rust.shape_active:
            raise ArgumentValidationError("begin_shape() cannot be nested.")
        self.state.rust.begin_shape_capture(None if kind is None else kind.value)

    def _reset_shape_capture(self) -> None:
        self.state.rust.reset_shape_capture()

    def _active_shape_vertices(self) -> list[tuple[float, float]]:
        return [tuple(point) for point in self.state.rust.active_vertices()]

    def _extend_shape_vertices(self, vertices: list[tuple[float, float]]) -> None:
        self.state.rust.extend_vertices(vertices)

    @contextmanager
    def shape(
        self, mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None
    ) -> Generator[None]:
        self.begin_shape(kind)
        completed = False
        try:
            yield
            self.end_shape(mode)
            completed = True
        finally:
            if not completed and self.state.rust.shape_active:
                self._reset_shape_capture()

    def vertex(self, x: float, y: float) -> None:
        if not self.state.rust.shape_active:
            raise ArgumentValidationError(
                "vertex() must be called between begin_shape() and end_shape()."
            )
        self.state.rust.add_vertex(float(x), float(y))

    def bezier_vertex(
        self, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float
    ) -> None:
        vertices = self._active_shape_vertices()
        if not vertices:
            raise ArgumentValidationError("bezier_vertex() requires an initial vertex().")
        p0 = vertices[-1]
        self._extend_shape_vertices(flatten_cubic(p0, (x2, y2), (x3, y3), (x4, y4)))

    def quadratic_vertex(self, cx: float, cy: float, x3: float, y3: float) -> None:
        vertices = self._active_shape_vertices()
        if not vertices:
            raise ArgumentValidationError("quadratic_vertex() requires an initial vertex().")
        p0 = vertices[-1]
        self._extend_shape_vertices(flatten_quadratic(p0, (cx, cy), (x3, y3)))

    def spline_vertex(self, x: float, y: float) -> None:
        if not self.state.rust.shape_active:
            raise ArgumentValidationError(
                "spline_vertex() must be called between begin_shape() and end_shape()."
            )
        vertices = self._active_shape_vertices()
        point = (float(x), float(y))
        if not vertices:
            self.state.rust.add_vertex(*point)
            return
        if len(vertices) == 1:
            self.state.rust.add_vertex(*point)
            return
        p0 = vertices[-2]
        p1 = vertices[-1]
        self._extend_shape_vertices(
            flatten_spline(p0, p1, point, point, tightness=self._spline_tightness)
        )

    def spline(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        x4: float,
        y4: float,
    ) -> None:
        p0 = (float(x1), float(y1))
        p1 = (float(x2), float(y2))
        p2 = (float(x3), float(y3))
        p3 = (float(x4), float(y4))
        previous_fill = self.state.style.fill_color
        self.state.style.fill_color = None
        cast(SketchContextHost, self)._mark_style_changed()
        self.renderer.polygon(
            [p1, *flatten_spline(p0, p1, p2, p3, tightness=self._spline_tightness)],
            self.state.style,
            self.state.transform.matrix,
            close=False,
        )
        self.state.style.fill_color = previous_fill
        cast(SketchContextHost, self)._mark_style_changed()

    def spline_point(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        return geometry_spline_point(
            float(a), float(b), float(cc), float(d), float(t), self._spline_tightness
        )

    def spline_tangent(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        return geometry_spline_tangent(
            float(a), float(b), float(cc), float(d), float(t), self._spline_tightness
        )

    def spline_property(self, name: str, value: float | None = None) -> float:
        if name != "tightness":
            raise ArgumentValidationError("Only spline_property('tightness') is supported.")
        if value is not None:
            self._spline_tightness = float(value)
        return self._spline_tightness

    def spline_properties(self, **properties: float) -> dict[str, float]:
        for name, value in properties.items():
            self.spline_property(name, value)
        return {"tightness": self._spline_tightness}

    def end_shape(self, mode: c.ArcMode = c.OPEN) -> None:
        if not self.state.rust.shape_active:
            raise ArgumentValidationError("end_shape() requires begin_shape().")
        if self.state.rust.contour_active:
            raise ArgumentValidationError("end_shape() requires end_contour() first.")
        draw_captured = getattr(self.renderer, "draw_captured_shape", None)
        if callable(draw_captured):
            draw_captured(
                self.state.rust,
                self.state.style,
                self.state.transform.matrix,
                close=mode == c.CLOSE,
            )
            return
        contours = [list(contour) for contour in self.state.rust.shape_contours()]
        vertices = [tuple(point) for point in self.state.rust.shape_vertices()]
        try:
            if contours:
                self.renderer.complex_polygon(
                    vertices,
                    contours,
                    self.state.style,
                    self.state.transform.matrix,
                    close=mode == c.CLOSE,
                )
            else:
                self.renderer.polygon(
                    vertices,
                    self.state.style,
                    self.state.transform.matrix,
                    close=mode == c.CLOSE,
                )
        finally:
            self._reset_shape_capture()

    def begin_contour(self) -> None:
        if not self.state.rust.shape_active:
            raise ArgumentValidationError("begin_contour() requires begin_shape().")
        if self.state.rust.contour_active:
            raise ArgumentValidationError("begin_contour() cannot be nested.")
        if self.state.rust.shape_kind is not None:
            raise ArgumentValidationError(
                "begin_contour() is supported only for freeform begin_shape() paths."
            )
        if self.state.rust.shape_vertex_count() < 3:
            raise ArgumentValidationError(
                "begin_contour() requires at least three outer shape vertices first."
            )
        self.state.rust.begin_contour_capture()

    def end_contour(self) -> None:
        if not self.state.rust.shape_active or not self.state.rust.contour_active:
            raise ArgumentValidationError("end_contour() requires begin_contour().")
        if self.state.rust.contour_vertex_count() < 3:
            raise ArgumentValidationError("end_contour() requires at least three vertices.")
        self.state.rust.end_contour_capture()

    @contextmanager
    def contour(self) -> Generator[None]:
        self.begin_contour()
        completed = False
        try:
            yield
            self.end_contour()
            completed = True
        finally:
            if not completed and self.state.rust.contour_active:
                self.state.rust.reset_contour_capture()

    def begin_clip(self) -> None:
        if self.state.rust.shape_active:
            raise ArgumentValidationError("begin_clip() cannot be called inside begin_shape().")
        self.begin_shape()

    def clip(self) -> None:
        if not self.state.rust.shape_active:
            raise ArgumentValidationError("clip() requires begin_clip().")
        if self.state.rust.contour_active:
            raise ArgumentValidationError("clip() requires end_contour() first.")
        begin_clip_captured = getattr(self.renderer, "begin_clip_captured_shape", None)
        if callable(begin_clip_captured):
            begin_clip_captured(self.state.rust, self.state.transform.matrix)
            return
        try:
            self.renderer.begin_clip(
                [tuple(point) for point in self.state.rust.shape_vertices()],
                [list(contour) for contour in self.state.rust.shape_contours()],
                self.state.transform.matrix,
            )
        finally:
            self._reset_shape_capture()

    def end_clip(self) -> None:
        self.renderer.end_clip()

    @contextmanager
    def clip_path(self) -> Generator[None]:
        self.begin_clip()
        completed = False
        try:
            yield
            self.clip()
            completed = True
        finally:
            if not completed and self.state.rust.shape_active:
                self._reset_shape_capture()

    def bezier(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        x4: float,
        y4: float,
    ) -> None:
        p0 = (float(x1), float(y1))
        p1 = (float(x2), float(y2))
        p2 = (float(x3), float(y3))
        p3 = (float(x4), float(y4))
        previous_fill = self.state.style.fill_color
        self.state.style.fill_color = None
        cast(SketchContextHost, self)._mark_style_changed()
        self.renderer.polygon(
            [p0, *flatten_cubic(p0, p1, p2, p3)],
            self.state.style,
            self.state.transform.matrix,
            close=False,
        )
        self.state.style.fill_color = previous_fill
        cast(SketchContextHost, self)._mark_style_changed()
