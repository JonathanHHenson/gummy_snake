"""Global-mode shape and curve wrappers."""

from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from typing import Any, Protocol, cast, overload

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.api.global_mode.helpers import xy
from gummysnake.core import geometry as _geometry


class PointLike(Protocol):
    """Public PointLike value."""
    x: float
    y: float


CoordinatePair = Sequence[float] | PointLike
_PRIMITIVE_RECT = 1
_PRIMITIVE_TRIANGLE = 2
_PRIMITIVE_ELLIPSE = 3


def _queue_fill_primitive(context: Any, kind: int, coords: tuple[float, ...]) -> bool:
    queue = getattr(context.renderer, "queue_fill_primitive_fast_path", None)
    if not callable(queue):
        return False
    return bool(queue(kind, coords, context.state.style, context.state.transform.matrix))


@overload
def point(position: CoordinatePair, /) -> None:
    """Overload accepting point coordinates or a point-like value.
    
    Args:
        position: The position value. Expected type: `CoordinatePair`.
    
    Returns:
        None.
    """
    ...


@overload
def point(x: float, y: float, /) -> None:
    """Overload accepting point coordinates or a point-like value.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
    
    Returns:
        None.
    """
    ...


def point(x: Any, y: float | None = None) -> None:
    """Draw a point.
    
    Args:
        x: The x value. Expected type: `Any`.
        y: The y value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        None.
    """
    px, py = xy(x, y)
    require_context().point(px, py)


@overload
def line(start: CoordinatePair, end: CoordinatePair, /) -> None:
    """Overload accepting line endpoints as coordinates or point-like values.
    
    Args:
        start: The start value. Expected type: `CoordinatePair`.
        end: The end value. Expected type: `CoordinatePair`.
    
    Returns:
        None.
    """
    ...


@overload
def line(x1: float, y1: float, x2: float, y2: float, /) -> None:
    """Overload accepting line endpoints as coordinates or point-like values.
    
    Args:
        x1: The x1 value. Expected type: `float`.
        y1: The y1 value. Expected type: `float`.
        x2: The x2 value. Expected type: `float`.
        y2: The y2 value. Expected type: `float`.
    
    Returns:
        None.
    """
    ...


def line(*args: Any) -> None:
    """Draw a line segment.
    
    Args:
        *args: Additional positional arguments. Expected type: `Any`.
    
    Returns:
        None.
    """
    if len(args) == 2:
        x1, y1 = xy(args[0])
        x2, y2 = xy(args[1])
    elif len(args) == 4:
        x1, y1, x2, y2 = (float(cast(float, value)) for value in args)
    else:
        raise TypeError("line() requires two points or four coordinate values.")
    require_context().line(x1, y1, x2, y2)


def rect(x: float, y: float, w: float, h: float | None = None) -> None:
    """Draw a rectangle.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        w: The w value. Expected type: `float`.
        h: The h value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        None.
    """
    context = require_context()
    if h is not None and context.state.style.rect_mode == c.CORNER:
        if _queue_fill_primitive(
            context,
            _PRIMITIVE_RECT,
            (float(x), float(y), float(w), float(h), 0.0, 0.0),
        ):
            return
        context.renderer.rect(
            float(x),
            float(y),
            float(w),
            float(h),
            context.state.style,
            context.state.transform.matrix,
        )
        return
    context.rect(x, y, w, h)


def square(x: float, y: float, size: float) -> None:
    """Draw a square.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        size: The size value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().square(x, y, size)


def ellipse(x: float, y: float, w: float, h: float | None = None) -> None:
    """Draw an ellipse.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        w: The w value. Expected type: `float`.
        h: The h value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        None.
    """
    require_context().ellipse(x, y, w, h)


def circle(x: float, y: float, diameter: float) -> None:
    """Draw a circle.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        diameter: The diameter value. Expected type: `float`.
    
    Returns:
        None.
    """
    context = require_context()
    if context.state.style.ellipse_mode == c.CENTER:
        d = float(diameter)
        if _queue_fill_primitive(
            context,
            _PRIMITIVE_ELLIPSE,
            (float(x) - d / 2.0, float(y) - d / 2.0, d, d, 0.0, 0.0),
        ):
            return
        context.renderer.ellipse(
            float(x) - d / 2.0,
            float(y) - d / 2.0,
            d,
            d,
            context.state.style,
            context.state.transform.matrix,
        )
        return
    context.circle(x, y, diameter)


@overload
def triangle(p1: CoordinatePair, p2: CoordinatePair, p3: CoordinatePair, /) -> None:
    """Overload accepting triangle vertices as coordinates or point-like values.
    
    Args:
        p1: The p1 value. Expected type: `CoordinatePair`.
        p2: The p2 value. Expected type: `CoordinatePair`.
        p3: The p3 value. Expected type: `CoordinatePair`.
    
    Returns:
        None.
    """
    ...


@overload
def triangle(x1: float, y1: float, x2: float, y2: float, x3: float, y3: float, /) -> None:
    """Overload accepting triangle vertices as coordinates or point-like values.
    
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
    ...


def triangle(*coords: Any) -> None:
    """Draw a triangle.
    
    Args:
        *coords: Additional positional arguments. Expected type: `Any`.
    
    Returns:
        None.
    """
    if len(coords) == 3:
        points = [xy(point) for point in coords]
        require_context().triangle(*(value for point in points for value in point))
        return
    if len(coords) == 6:
        context = require_context()
        values = (
            float(cast(float, coords[0])),
            float(cast(float, coords[1])),
            float(cast(float, coords[2])),
            float(cast(float, coords[3])),
            float(cast(float, coords[4])),
            float(cast(float, coords[5])),
        )
        if _queue_fill_primitive(context, _PRIMITIVE_TRIANGLE, values):
            return
        context.renderer.triangle(
            values[0],
            values[1],
            values[2],
            values[3],
            values[4],
            values[5],
            context.state.style,
            context.state.transform.matrix,
        )
        return
    raise TypeError("triangle() requires three points or six coordinate values.")


@overload
def quad(
    p1: CoordinatePair, p2: CoordinatePair, p3: CoordinatePair, p4: CoordinatePair, /
) -> None:
    """Overload accepting quadrilateral vertices as coordinates or point-like values.
    
    Args:
        p1: The p1 value. Expected type: `CoordinatePair`.
        p2: The p2 value. Expected type: `CoordinatePair`.
        p3: The p3 value. Expected type: `CoordinatePair`.
        p4: The p4 value. Expected type: `CoordinatePair`.
    
    Returns:
        None.
    """
    ...


@overload
def quad(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
    x4: float,
    y4: float,
    /,
) -> None:
    """Overload accepting quadrilateral vertices as coordinates or point-like values.
    
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
    ...


def quad(*coords: Any) -> None:
    """Draw a quadrilateral.
    
    Args:
        *coords: Additional positional arguments. Expected type: `Any`.
    
    Returns:
        None.
    """
    if len(coords) == 4:
        points = [xy(point) for point in coords]
        require_context().quad(*(value for point in points for value in point))
        return
    if len(coords) == 8:
        require_context().quad(*(float(cast(float, value)) for value in coords))
        return
    raise TypeError("quad() requires four points or eight coordinate values.")


def arc(
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
    require_context().arc(x, y, width, height, start, stop, mode)


def begin_shape(kind: c.ShapeKind | None = None) -> None:
    """Start capturing a custom shape.
    
    Args:
        kind: The kind value. Expected type: `c.ShapeKind | None`. Defaults to `None`.
    
    Returns:
        None.
    """
    require_context().begin_shape(kind)


@contextmanager
def shape(mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None) -> Generator[None]:
    """Capture and draw a custom shape in a context manager.
    
    Args:
        mode: The mode value. Expected type: `c.ArcMode`. Defaults to `c.OPEN`.
        kind: The kind value. Expected type: `c.ShapeKind | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Generator[None]`.
    """
    with require_context().shape(mode, kind=kind):
        yield


def begin_contour() -> None:
    """Start a contour inside the active shape.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().begin_contour()


@contextmanager
def contour() -> Generator[None]:
    """Capture a shape contour in a context manager.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `Generator[None]`.
    """
    with require_context().contour():
        yield


def end_contour() -> None:
    """Finish the active contour.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().end_contour()


def begin_clip() -> None:
    """Start capturing a clipping path.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().begin_clip()


@contextmanager
def clip_path() -> Generator[None]:
    """Capture a clipping path in a context manager.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `Generator[None]`.
    """
    with require_context().clip_path():
        yield


def clip() -> None:
    """Apply the currently captured clip path.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().clip()


def end_clip() -> None:
    """Finish the active clipping path.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().end_clip()


def vertex(x: float, y: float) -> None:
    """Add a vertex to the active shape.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().vertex(x, y)


def bezier_vertex(x2: float, y2: float, x3: float, y3: float, x4: float, y4: float) -> None:
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
    require_context().bezier_vertex(x2, y2, x3, y3, x4, y4)


def quadratic_vertex(cx: float, cy: float, x3: float, y3: float) -> None:
    """Add a quadratic Bézier vertex segment to the active shape.
    
    Args:
        cx: The cx value. Expected type: `float`.
        cy: The cy value. Expected type: `float`.
        x3: The x3 value. Expected type: `float`.
        y3: The y3 value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().quadratic_vertex(cx, cy, x3, y3)


def spline_vertex(x: float, y: float) -> None:
    """Add a spline vertex to the active shape.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().spline_vertex(x, y)


def end_shape(mode: c.ArcMode = c.OPEN) -> None:
    """Finish and draw the active shape.
    
    Args:
        mode: The mode value. Expected type: `c.ArcMode`. Defaults to `c.OPEN`.
    
    Returns:
        None.
    """
    require_context().end_shape(mode)


def bezier(
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
    require_context().bezier(x1, y1, x2, y2, x3, y3, x4, y4)


def spline(
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
    require_context().spline(x1, y1, x2, y2, x3, y3, x4, y4)


def bezier_point(a: float, b: float, c: float, d: float, t: float) -> float:
    """Evaluate a cubic Bézier curve at a parameter.
    
    Args:
        a: The a value. Expected type: `float`.
        b: The b value. Expected type: `float`.
        c: The c value. Expected type: `float`.
        d: The d value. Expected type: `float`.
        t: The t value. Expected type: `float`.
    
    Returns:
        The return value. Type: `float`.
    """
    return _geometry.bezier_point(a, b, c, d, t)


def bezier_tangent(a: float, b: float, c: float, d: float, t: float) -> float:
    """Evaluate a cubic Bézier tangent at a parameter.
    
    Args:
        a: The a value. Expected type: `float`.
        b: The b value. Expected type: `float`.
        c: The c value. Expected type: `float`.
        d: The d value. Expected type: `float`.
        t: The t value. Expected type: `float`.
    
    Returns:
        The return value. Type: `float`.
    """
    return _geometry.bezier_tangent(a, b, c, d, t)


def spline_point(a: float, b: float, c: float, d: float, t: float) -> float:
    """Evaluate a spline curve at a parameter.
    
    Args:
        a: The a value. Expected type: `float`.
        b: The b value. Expected type: `float`.
        c: The c value. Expected type: `float`.
        d: The d value. Expected type: `float`.
        t: The t value. Expected type: `float`.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().spline_point(a, b, c, d, t)


def spline_tangent(a: float, b: float, c: float, d: float, t: float) -> float:
    """Evaluate a spline tangent at a parameter.
    
    Args:
        a: The a value. Expected type: `float`.
        b: The b value. Expected type: `float`.
        c: The c value. Expected type: `float`.
        d: The d value. Expected type: `float`.
        t: The t value. Expected type: `float`.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().spline_tangent(a, b, c, d, t)


def spline_property(name: str, value: float | None = None) -> float:
    """Get or set a spline property.
    
    Args:
        name: The name value. Expected type: `str`.
        value: The value value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `float`.
    """
    return require_context().spline_property(name, value)


def spline_properties(**properties: float) -> dict[str, float]:
    """Set and return spline properties.
    
    Args:
        **properties: Additional keyword arguments. Expected type: `float`.
    
    Returns:
        The return value. Type: `dict[str, float]`.
    """
    return require_context().spline_properties(**properties)
