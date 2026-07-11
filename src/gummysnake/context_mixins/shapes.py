"""2D primitive and curve drawing methods for SketchContext."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

from gummysnake import constants as c
from gummysnake.context_mixins._protocols import SketchContextHost
from gummysnake.context_mixins.shape_support.capture import (
    active_shape_vertices as _active_shape_vertices_impl,
)
from gummysnake.context_mixins.shape_support.capture import begin_clip as _begin_clip_impl
from gummysnake.context_mixins.shape_support.capture import begin_contour as _begin_contour_impl
from gummysnake.context_mixins.shape_support.capture import begin_shape as _begin_shape_impl
from gummysnake.context_mixins.shape_support.capture import bezier_vertex as _bezier_vertex_impl
from gummysnake.context_mixins.shape_support.capture import clip as _clip_impl
from gummysnake.context_mixins.shape_support.capture import clip_path as _clip_path_impl
from gummysnake.context_mixins.shape_support.capture import contour as _contour_impl
from gummysnake.context_mixins.shape_support.capture import end_clip as _end_clip_impl
from gummysnake.context_mixins.shape_support.capture import end_contour as _end_contour_impl
from gummysnake.context_mixins.shape_support.capture import end_shape as _end_shape_impl
from gummysnake.context_mixins.shape_support.capture import (
    quadratic_vertex as _quadratic_vertex_impl,
)
from gummysnake.context_mixins.shape_support.capture import (
    reset_shape_capture as _reset_shape_capture_impl,
)
from gummysnake.context_mixins.shape_support.capture import shape as _shape_impl
from gummysnake.context_mixins.shape_support.capture import spline_vertex as _spline_vertex_impl
from gummysnake.context_mixins.shape_support.capture import vertex as _vertex_impl
from gummysnake.context_mixins.shape_support.curves import bezier as _bezier_impl
from gummysnake.context_mixins.shape_support.curves import spline as _spline_impl
from gummysnake.context_mixins.shape_support.curves import spline_point as _spline_point_impl
from gummysnake.context_mixins.shape_support.curves import (
    spline_properties as _spline_properties_impl,
)
from gummysnake.context_mixins.shape_support.curves import spline_property as _spline_property_impl
from gummysnake.context_mixins.shape_support.curves import spline_tangent as _spline_tangent_impl
from gummysnake.core.geometry import resolve_ellipse, resolve_rect


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
        _begin_shape_impl(self, kind)

    def _reset_shape_capture(self) -> None:
        _reset_shape_capture_impl(self)

    def _active_shape_vertices(self) -> list[tuple[float, float]]:
        return _active_shape_vertices_impl(self)

    @contextmanager
    def shape(
        self, mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None
    ) -> Generator[None]:
        with _shape_impl(self, mode, kind=kind):
            yield

    def vertex(self, x: float, y: float) -> None:
        _vertex_impl(self, x, y)

    def bezier_vertex(
        self, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float
    ) -> None:
        _bezier_vertex_impl(self, x2, y2, x3, y3, x4, y4)

    def quadratic_vertex(self, cx: float, cy: float, x3: float, y3: float) -> None:
        _quadratic_vertex_impl(self, cx, cy, x3, y3)

    def spline_vertex(self, x: float, y: float) -> None:
        _spline_vertex_impl(self, x, y)

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
        _spline_impl(self, x1, y1, x2, y2, x3, y3, x4, y4)

    def spline_point(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        return _spline_point_impl(self, a, b, cc, d, t)

    def spline_tangent(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        return _spline_tangent_impl(self, a, b, cc, d, t)

    def spline_property(self, name: str, value: float | None = None) -> float:
        return _spline_property_impl(self, name, value)

    def spline_properties(self, **properties: float) -> dict[str, float]:
        return _spline_properties_impl(self, **properties)

    def end_shape(self, mode: c.ArcMode = c.OPEN) -> None:
        _end_shape_impl(self, mode)

    def begin_contour(self) -> None:
        _begin_contour_impl(self)

    def end_contour(self) -> None:
        _end_contour_impl(self)

    @contextmanager
    def contour(self) -> Generator[None]:
        with _contour_impl(self):
            yield

    def begin_clip(self) -> None:
        _begin_clip_impl(self)

    def clip(self) -> None:
        _clip_impl(self)

    def end_clip(self) -> None:
        _end_clip_impl(self)

    @contextmanager
    def clip_path(self) -> Generator[None]:
        with _clip_path_impl(self):
            yield

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
        _bezier_impl(self, x1, y1, x2, y2, x3, y3, x4, y4)
