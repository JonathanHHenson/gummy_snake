"""2D primitive and curve drawing methods for SketchContext."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

from gummysnake import constants as c
from gummysnake.context_mixins._protocols import SketchContextHost
from gummysnake.context_mixins.shape_capture import (
    active_shape_vertices as _active_shape_vertices_impl,
)
from gummysnake.context_mixins.shape_capture import begin_clip as _begin_clip_impl
from gummysnake.context_mixins.shape_capture import begin_contour as _begin_contour_impl
from gummysnake.context_mixins.shape_capture import begin_shape as _begin_shape_impl
from gummysnake.context_mixins.shape_capture import bezier_vertex as _bezier_vertex_impl
from gummysnake.context_mixins.shape_capture import clip as _clip_impl
from gummysnake.context_mixins.shape_capture import clip_path as _clip_path_impl
from gummysnake.context_mixins.shape_capture import contour as _contour_impl
from gummysnake.context_mixins.shape_capture import end_clip as _end_clip_impl
from gummysnake.context_mixins.shape_capture import end_contour as _end_contour_impl
from gummysnake.context_mixins.shape_capture import end_shape as _end_shape_impl
from gummysnake.context_mixins.shape_capture import (
    extend_shape_vertices as _extend_shape_vertices_impl,
)
from gummysnake.context_mixins.shape_capture import quadratic_vertex as _quadratic_vertex_impl
from gummysnake.context_mixins.shape_capture import reset_shape_capture as _reset_shape_capture_impl
from gummysnake.context_mixins.shape_capture import shape as _shape_impl
from gummysnake.context_mixins.shape_capture import spline_vertex as _spline_vertex_impl
from gummysnake.context_mixins.shape_capture import vertex as _vertex_impl
from gummysnake.context_mixins.shape_curves import bezier as _bezier_impl
from gummysnake.context_mixins.shape_curves import spline as _spline_impl
from gummysnake.context_mixins.shape_curves import spline_point as _spline_point_impl
from gummysnake.context_mixins.shape_curves import spline_properties as _spline_properties_impl
from gummysnake.context_mixins.shape_curves import spline_property as _spline_property_impl
from gummysnake.context_mixins.shape_curves import spline_tangent as _spline_tangent_impl
from gummysnake.core.geometry import resolve_ellipse, resolve_rect


class ShapeContextMixin:
    renderer: Any
    state: Any
    _spline_tightness: float

    def point(self, x: float, y: float) -> None:
        """Point.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
        
        Returns:
            None.
        """
        self.renderer.point(float(x), float(y), self.state.style, self.state.transform.matrix)

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Line.
        
        Args:
            x1: The x1 value. Expected type: `float`.
            y1: The y1 value. Expected type: `float`.
            x2: The x2 value. Expected type: `float`.
            y2: The y2 value. Expected type: `float`.
        
        Returns:
            None.
        """
        self.renderer.line(
            float(x1),
            float(y1),
            float(x2),
            float(y2),
            self.state.style,
            self.state.transform.matrix,
        )

    def rect(self, x: float, y: float, width: float, height: float | None = None) -> None:
        """Rect.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        h = width if height is None else height
        rx, ry, rw, rh = resolve_rect(
            self.state.style.rect_mode, float(x), float(y), float(width), float(h)
        )
        self.renderer.rect(rx, ry, rw, rh, self.state.style, self.state.transform.matrix)

    def square(self, x: float, y: float, size: float) -> None:
        """Square.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            size: The size value. Expected type: `float`.
        
        Returns:
            None.
        """
        self.rect(x, y, size, size)

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None:
        """Ellipse.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        h = width if height is None else height
        ex, ey, ew, eh = resolve_ellipse(
            self.state.style.ellipse_mode, float(x), float(y), float(width), float(h)
        )
        self.renderer.ellipse(ex, ey, ew, eh, self.state.style, self.state.transform.matrix)

    def circle(self, x: float, y: float, diameter: float) -> None:
        """Circle.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            diameter: The diameter value. Expected type: `float`.
        
        Returns:
            None.
        """
        self.ellipse(x, y, diameter, diameter)

    def triangle(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
        """Triangle.
        
        Args:
            x1: The x1 value. Expected type: `float`.
            y1: The y1 value. Expected type: `float`.
            x2: The x2 value. Expected type: `float`.
            y2: The y2 value. Expected type: `float`.
            x3: The x3 value. Expected type: `float`.
            y3: The y3 value. Expected type: `float`.
        
        Returns:
            None.
        """
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
        """Quad.
        
        Args:
            x1: The x1 value. Expected type: `float`.
            y1: The y1 value. Expected type: `float`.
            x2: The x2 value. Expected type: `float`.
            y2: The y2 value. Expected type: `float`.
            x3: The x3 value. Expected type: `float`.
            y3: The y3 value. Expected type: `float`.
            x4: The x4 value. Expected type: `float`.
            y4: The y4 value. Expected type: `float`.
        
        Returns:
            None.
        """
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
        """Arc.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float`.
            start: The start value. Expected type: `float`.
            stop: The stop value. Expected type: `float`.
            mode: The mode value. Expected type: `c.ArcMode`. Defaults to `c.OPEN`.
        
        Returns:
            None.
        """
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
        """Begin shape.
        
        Args:
            kind: The kind value. Expected type: `c.ShapeKind | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        _begin_shape_impl(self, kind)

    def _reset_shape_capture(self) -> None:
        _reset_shape_capture_impl(self)

    def _active_shape_vertices(self) -> list[tuple[float, float]]:
        return _active_shape_vertices_impl(self)

    def _extend_shape_vertices(self, vertices: list[tuple[float, float]]) -> None:
        _extend_shape_vertices_impl(self, vertices)

    @contextmanager
    def shape(
        self, mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None
    ) -> Generator[None]:
        """Shape.
        
        Args:
            mode: The mode value. Expected type: `c.ArcMode`. Defaults to `c.OPEN`.
            kind: The kind value. Expected type: `c.ShapeKind | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Generator[None]`.
        """
        with _shape_impl(self, mode, kind=kind):
            yield

    def vertex(self, x: float, y: float) -> None:
        """Vertex.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
        
        Returns:
            None.
        """
        _vertex_impl(self, x, y)

    def bezier_vertex(
        self, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float
    ) -> None:
        """Bezier vertex.
        
        Args:
            x2: The x2 value. Expected type: `float`.
            y2: The y2 value. Expected type: `float`.
            x3: The x3 value. Expected type: `float`.
            y3: The y3 value. Expected type: `float`.
            x4: The x4 value. Expected type: `float`.
            y4: The y4 value. Expected type: `float`.
        
        Returns:
            None.
        """
        _bezier_vertex_impl(self, x2, y2, x3, y3, x4, y4)

    def quadratic_vertex(self, cx: float, cy: float, x3: float, y3: float) -> None:
        """Quadratic vertex.
        
        Args:
            cx: The cx value. Expected type: `float`.
            cy: The cy value. Expected type: `float`.
            x3: The x3 value. Expected type: `float`.
            y3: The y3 value. Expected type: `float`.
        
        Returns:
            None.
        """
        _quadratic_vertex_impl(self, cx, cy, x3, y3)

    def spline_vertex(self, x: float, y: float) -> None:
        """Spline vertex.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
        
        Returns:
            None.
        """
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
        """Spline.
        
        Args:
            x1: The x1 value. Expected type: `float`.
            y1: The y1 value. Expected type: `float`.
            x2: The x2 value. Expected type: `float`.
            y2: The y2 value. Expected type: `float`.
            x3: The x3 value. Expected type: `float`.
            y3: The y3 value. Expected type: `float`.
            x4: The x4 value. Expected type: `float`.
            y4: The y4 value. Expected type: `float`.
        
        Returns:
            None.
        """
        _spline_impl(self, x1, y1, x2, y2, x3, y3, x4, y4)

    def spline_point(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        """Spline point.
        
        Args:
            a: The a value. Expected type: `float`.
            b: The b value. Expected type: `float`.
            cc: The cc value. Expected type: `float`.
            d: The d value. Expected type: `float`.
            t: The t value. Expected type: `float`.
        
        Returns:
            The return value. Type: `float`.
        """
        return _spline_point_impl(self, a, b, cc, d, t)

    def spline_tangent(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        """Spline tangent.
        
        Args:
            a: The a value. Expected type: `float`.
            b: The b value. Expected type: `float`.
            cc: The cc value. Expected type: `float`.
            d: The d value. Expected type: `float`.
            t: The t value. Expected type: `float`.
        
        Returns:
            The return value. Type: `float`.
        """
        return _spline_tangent_impl(self, a, b, cc, d, t)

    def spline_property(self, name: str, value: float | None = None) -> float:
        """Spline property.
        
        Args:
            name: The name value. Expected type: `str`.
            value: The value value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        return _spline_property_impl(self, name, value)

    def spline_properties(self, **properties: float) -> dict[str, float]:
        """Spline properties.
        
        Args:
            **properties: Additional keyword arguments. Expected type: `float`.
        
        Returns:
            The return value. Type: `dict[str, float]`.
        """
        return _spline_properties_impl(self, **properties)

    def end_shape(self, mode: c.ArcMode = c.OPEN) -> None:
        """End shape.
        
        Args:
            mode: The mode value. Expected type: `c.ArcMode`. Defaults to `c.OPEN`.
        
        Returns:
            None.
        """
        _end_shape_impl(self, mode)

    def begin_contour(self) -> None:
        """Begin contour.
        
        Args:
            None.
        
        Returns:
            None.
        """
        _begin_contour_impl(self)

    def end_contour(self) -> None:
        """End contour.
        
        Args:
            None.
        
        Returns:
            None.
        """
        _end_contour_impl(self)

    @contextmanager
    def contour(self) -> Generator[None]:
        """Contour.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Generator[None]`.
        """
        with _contour_impl(self):
            yield

    def begin_clip(self) -> None:
        """Begin clip.
        
        Args:
            None.
        
        Returns:
            None.
        """
        _begin_clip_impl(self)

    def clip(self) -> None:
        """Clip.
        
        Args:
            None.
        
        Returns:
            None.
        """
        _clip_impl(self)

    def end_clip(self) -> None:
        """End clip.
        
        Args:
            None.
        
        Returns:
            None.
        """
        _end_clip_impl(self)

    @contextmanager
    def clip_path(self) -> Generator[None]:
        """Clip path.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Generator[None]`.
        """
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
        """Bezier.
        
        Args:
            x1: The x1 value. Expected type: `float`.
            y1: The y1 value. Expected type: `float`.
            x2: The x2 value. Expected type: `float`.
            y2: The y2 value. Expected type: `float`.
            x3: The x3 value. Expected type: `float`.
            y3: The y3 value. Expected type: `float`.
            x4: The x4 value. Expected type: `float`.
            y4: The y4 value. Expected type: `float`.
        
        Returns:
            None.
        """
        _bezier_impl(self, x1, y1, x2, y2, x3, y3, x4, y4)
