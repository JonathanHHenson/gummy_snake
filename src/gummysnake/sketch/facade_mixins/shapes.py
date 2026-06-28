"""2D shape forwards for object sketches."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from gummysnake import constants as c
from gummysnake.core import geometry as _geometry
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeShapesMixin(SketchFacadeBaseMixin):
    """Public SketchFacadeShapesMixin value."""
    def point(self, x: float, y: float) -> None:
        """Draw a point.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.point(x, y)

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Draw a line segment.
        
        Args:
            x1: The x1 value. Expected type: `float`.
            y1: The y1 value. Expected type: `float`.
            x2: The x2 value. Expected type: `float`.
            y2: The y2 value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.line(x1, y1, x2, y2)

    def rect(self, x: float, y: float, width: float, height: float | None = None) -> None:
        """Draw a rectangle.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        self._ctx.rect(x, y, width, height)

    def square(self, x: float, y: float, size: float) -> None:
        """Draw a square.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            size: The size value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.square(x, y, size)

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None:
        """Draw an ellipse.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            width: The width value. Expected type: `float`.
            height: The height value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        self._ctx.ellipse(x, y, width, height)

    def circle(self, x: float, y: float, diameter: float) -> None:
        """Draw a circle.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
            diameter: The diameter value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.circle(x, y, diameter)

    def triangle(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
        """Draw a triangle.
        
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
        """Draw a quadrilateral.
        
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
        """Draw an arc.
        
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
        self._ctx.arc(x, y, width, height, start, stop, mode)

    def begin_shape(self, kind: c.ShapeKind | None = None) -> None:
        """Start capturing a custom shape.
        
        Args:
            kind: The kind value. Expected type: `c.ShapeKind | None`. Defaults to `None`.
        
        Returns:
            None.
        """
        self._ctx.begin_shape(kind)

    @contextmanager
    def shape(
        self, mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None
    ) -> Generator[None]:
        """Capture and draw a custom shape in a context manager.
        
        Args:
            mode: The mode value. Expected type: `c.ArcMode`. Defaults to `c.OPEN`.
            kind: The kind value. Expected type: `c.ShapeKind | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Generator[None]`.
        """
        with self._ctx.shape(mode, kind=kind):
            yield

    def begin_contour(self) -> None:
        """Start a contour inside the active shape.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.begin_contour()

    @contextmanager
    def contour(self) -> Generator[None]:
        """Capture a shape contour in a context manager.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Generator[None]`.
        """
        with self._ctx.contour():
            yield

    def end_contour(self) -> None:
        """Finish the active contour.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.end_contour()

    def begin_clip(self) -> None:
        """Start capturing a clipping path.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.begin_clip()

    @contextmanager
    def clip_path(self) -> Generator[None]:
        """Capture a clipping path in a context manager.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Generator[None]`.
        """
        with self._ctx.clip_path():
            yield

    def clip(self) -> None:
        """Apply the currently captured clip path.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.clip()

    def end_clip(self) -> None:
        """Finish the active clipping path.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.end_clip()

    def vertex(self, x: float, y: float) -> None:
        """Add a vertex to the active shape.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.vertex(x, y)

    def bezier_vertex(
        self, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float
    ) -> None:
        """Add a cubic Bézier vertex segment to the active shape.
        
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
        self._ctx.bezier_vertex(x2, y2, x3, y3, x4, y4)

    def quadratic_vertex(self, cx: float, cy: float, x3: float, y3: float) -> None:
        """Add a quadratic Bézier vertex segment to the active shape.
        
        Args:
            cx: The cx value. Expected type: `float`.
            cy: The cy value. Expected type: `float`.
            x3: The x3 value. Expected type: `float`.
            y3: The y3 value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.quadratic_vertex(cx, cy, x3, y3)

    def spline_vertex(self, x: float, y: float) -> None:
        """Add a spline vertex to the active shape.
        
        Args:
            x: The x value. Expected type: `float`.
            y: The y value. Expected type: `float`.
        
        Returns:
            None.
        """
        self._ctx.spline_vertex(x, y)

    def end_shape(self, mode: c.ArcMode = c.OPEN) -> None:
        """Finish and draw the active shape.
        
        Args:
            mode: The mode value. Expected type: `c.ArcMode`. Defaults to `c.OPEN`.
        
        Returns:
            None.
        """
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
        """Draw a cubic Bézier curve.
        
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
        """Draw a spline curve.
        
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
        self._ctx.spline(x1, y1, x2, y2, x3, y3, x4, y4)

    def bezier_point(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        """Evaluate a cubic Bézier curve at a parameter.
        
        Args:
            a: The a value. Expected type: `float`.
            b: The b value. Expected type: `float`.
            cc: The cc value. Expected type: `float`.
            d: The d value. Expected type: `float`.
            t: The t value. Expected type: `float`.
        
        Returns:
            The return value. Type: `float`.
        """
        return _geometry.bezier_point(a, b, cc, d, t)

    def bezier_tangent(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        """Evaluate a cubic Bézier tangent at a parameter.
        
        Args:
            a: The a value. Expected type: `float`.
            b: The b value. Expected type: `float`.
            cc: The cc value. Expected type: `float`.
            d: The d value. Expected type: `float`.
            t: The t value. Expected type: `float`.
        
        Returns:
            The return value. Type: `float`.
        """
        return _geometry.bezier_tangent(a, b, cc, d, t)

    def spline_point(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        """Evaluate a spline curve at a parameter.
        
        Args:
            a: The a value. Expected type: `float`.
            b: The b value. Expected type: `float`.
            cc: The cc value. Expected type: `float`.
            d: The d value. Expected type: `float`.
            t: The t value. Expected type: `float`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.spline_point(a, b, cc, d, t)

    def spline_tangent(self, a: float, b: float, cc: float, d: float, t: float) -> float:
        """Evaluate a spline tangent at a parameter.
        
        Args:
            a: The a value. Expected type: `float`.
            b: The b value. Expected type: `float`.
            cc: The cc value. Expected type: `float`.
            d: The d value. Expected type: `float`.
            t: The t value. Expected type: `float`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.spline_tangent(a, b, cc, d, t)

    def spline_property(self, name: str, value: float | None = None) -> float:
        """Get or set a spline property.
        
        Args:
            name: The name value. Expected type: `str`.
            value: The value value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.spline_property(name, value)

    def spline_properties(self, **properties: float) -> dict[str, float]:
        """Set and return spline properties.
        
        Args:
            **properties: Additional keyword arguments. Expected type: `float`.
        
        Returns:
            The return value. Type: `dict[str, float]`.
        """
        return self._ctx.spline_properties(**properties)
