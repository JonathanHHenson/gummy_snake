"""2D shape forwards for object sketches."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from gummysnake import constants as c
from gummysnake.core import geometry as _geometry
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeShapesMixin(SketchFacadeBaseMixin):
    def point(self, x: float, y: float) -> None:
        self._ctx.point(x, y)

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self._ctx.line(x1, y1, x2, y2)

    def rect(self, x: float, y: float, width: float, height: float | None = None) -> None:
        self._ctx.rect(x, y, width, height)

    def square(self, x: float, y: float, size: float) -> None:
        self._ctx.square(x, y, size)

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None:
        self._ctx.ellipse(x, y, width, height)

    def circle(self, x: float, y: float, diameter: float) -> None:
        self._ctx.circle(x, y, diameter)

    def triangle(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
        self._ctx.triangle(x1, y1, x2, y2, x3, y3)

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
        self._ctx.quad(x1, y1, x2, y2, x3, y3, x4, y4)

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
        self._ctx.arc(x, y, width, height, start, stop, mode)

    def begin_shape(self, kind: c.ShapeKind | None = None) -> None:
        self._ctx.begin_shape(kind)

    @contextmanager
    def shape(
        self, mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None
    ) -> Generator[None]:
        with self._ctx.shape(mode, kind=kind):
            yield

    def begin_contour(self) -> None:
        self._ctx.begin_contour()

    @contextmanager
    def contour(self) -> Generator[None]:
        with self._ctx.contour():
            yield

    def end_contour(self) -> None:
        self._ctx.end_contour()

    def begin_clip(self) -> None:
        self._ctx.begin_clip()

    @contextmanager
    def clip_path(self) -> Generator[None]:
        with self._ctx.clip_path():
            yield

    def clip(self) -> None:
        self._ctx.clip()

    def end_clip(self) -> None:
        self._ctx.end_clip()

    def vertex(self, x: float, y: float) -> None:
        self._ctx.vertex(x, y)

    def bezier_vertex(
        self, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float
    ) -> None:
        self._ctx.bezier_vertex(x2, y2, x3, y3, x4, y4)

    def quadratic_vertex(self, cx: float, cy: float, x3: float, y3: float) -> None:
        self._ctx.quadratic_vertex(cx, cy, x3, y3)

    def spline_vertex(self, x: float, y: float) -> None:
        self._ctx.spline_vertex(x, y)

    def end_shape(self, mode: c.ArcMode = c.OPEN) -> None:
        self._ctx.end_shape(mode)

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
        self._ctx.bezier(x1, y1, x2, y2, x3, y3, x4, y4)

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
        self._ctx.spline(x1, y1, x2, y2, x3, y3, x4, y4)

    def bezier_point(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        return _geometry.bezier_point(a, b, cc, d, t)

    def bezier_tangent(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        return _geometry.bezier_tangent(a, b, cc, d, t)

    def spline_point(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        return self._ctx.spline_point(a, b, cc, d, t)

    def spline_tangent(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        return self._ctx.spline_tangent(a, b, cc, d, t)

    def spline_property(self, name: str, value: float | None = None) -> float:
        return self._ctx.spline_property(name, value)

    def spline_properties(self, **properties: float) -> dict[str, float]:
        return self._ctx.spline_properties(**properties)
