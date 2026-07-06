"""Global-mode shape and curve wrappers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.api.global_mode.helpers import CoordinatePair, Number, xy
from gummysnake.core import geometry as _geometry

_PRIMITIVE_RECT = 1
_PRIMITIVE_TRIANGLE = 2
_PRIMITIVE_ELLIPSE = 3


def _queue_fill_primitive(context: Any, kind: int, coords: tuple[float, ...]) -> bool:
    """Try the renderer's fast path for simple filled shapes."""

    queue = getattr(context.renderer, "queue_fill_primitive_fast_path", None)
    if not callable(queue):
        return False
    return bool(queue(kind, coords, context.state.style, context.state.transform.matrix))


@overload
def point(position: CoordinatePair, /) -> None: ...


@overload
def point(x: float, y: float, /) -> None: ...


def point(x: CoordinatePair | Number, y: Number | None = None) -> None:
    """Draw a single point at a coordinate or point-like object."""

    if y is None:
        px, py = xy(cast(CoordinatePair, x))
    else:
        px, py = xy(cast(Number, x), y)
    require_context().point(px, py)


@overload
def line(start: CoordinatePair, end: CoordinatePair, /) -> None: ...


@overload
def line(x1: float, y1: float, x2: float, y2: float, /) -> None: ...


def line(*args: Any) -> None:
    """Draw a straight line between two points."""

    if len(args) == 2:
        x1, y1 = xy(args[0])
        x2, y2 = xy(args[1])
    elif len(args) == 4:
        x1, y1, x2, y2 = (float(cast(float, value)) for value in args)
    else:
        raise TypeError("line() requires two points or four coordinate values.")
    require_context().line(x1, y1, x2, y2)


def rect(x: float, y: float, w: float, h: float | None = None) -> None:
    """Draw a rectangle with the current style and rect mode."""

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
    """Draw a square with the current style and rect mode."""

    require_context().square(x, y, size)


def ellipse(x: float, y: float, w: float, h: float | None = None) -> None:
    """Draw an ellipse with the current style and ellipse mode."""

    require_context().ellipse(x, y, w, h)


def circle(x: float, y: float, diameter: float) -> None:
    """Draw a circle with the current style and ellipse mode."""

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
def triangle(p1: CoordinatePair, p2: CoordinatePair, p3: CoordinatePair, /) -> None: ...


@overload
def triangle(x1: float, y1: float, x2: float, y2: float, x3: float, y3: float, /) -> None: ...


def triangle(*coords: Any) -> None:
    """Draw a triangle from three points or six coordinates."""

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
) -> None: ...


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
) -> None: ...


def quad(*coords: Any) -> None:
    """Draw a four-sided shape from points or coordinates."""

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
    """Draw part of an ellipse between two angles."""

    require_context().arc(x, y, width, height, start, stop, mode)


def begin_shape(kind: c.ShapeKind | None = None) -> None:
    """Start collecting vertices for a custom shape."""

    require_context().begin_shape(kind)


@contextmanager
def shape(mode: c.ArcMode = c.OPEN, *, kind: c.ShapeKind | None = None) -> Generator[None]:
    """Build a custom shape inside a with block."""

    with require_context().shape(mode, kind=kind):
        yield


def begin_contour() -> None:
    """Start a contour, often used to make a hole in a shape."""

    require_context().begin_contour()


@contextmanager
def contour() -> Generator[None]:
    """Build a contour inside the current shape with a with block."""

    with require_context().contour():
        yield


def end_contour() -> None:
    """Finish the current contour."""

    require_context().end_contour()


def begin_clip() -> None:
    """Start collecting vertices for a clipping path."""

    require_context().begin_clip()


@contextmanager
def clip_path() -> Generator[None]:
    """Create a clipping path inside a with block."""

    with require_context().clip_path():
        yield


def clip() -> None:
    """Apply the current shape as a clipping path."""

    require_context().clip()


def end_clip() -> None:
    """Finish the current clipping path."""

    require_context().end_clip()


def vertex(x: float, y: float) -> None:
    """Add one vertex to the current custom shape."""

    require_context().vertex(x, y)


def bezier_vertex(x2: float, y2: float, x3: float, y3: float, x4: float, y4: float) -> None:
    """Add a cubic Bézier curve segment to the current shape."""

    require_context().bezier_vertex(x2, y2, x3, y3, x4, y4)


def quadratic_vertex(cx: float, cy: float, x3: float, y3: float) -> None:
    """Add a quadratic curve segment to the current shape."""

    require_context().quadratic_vertex(cx, cy, x3, y3)


def spline_vertex(x: float, y: float) -> None:
    """Add a spline control point to the current shape."""

    require_context().spline_vertex(x, y)


def end_shape(mode: c.ArcMode = c.OPEN) -> None:
    """Finish and draw the current custom shape."""

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
    """Draw a cubic Bézier curve through four control points."""

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
    """Draw a smooth spline through four control points."""

    require_context().spline(x1, y1, x2, y2, x3, y3, x4, y4)


def bezier_point(a: float, b: float, c: float, d: float, t: float) -> float:
    """Return one coordinate value on a cubic Bézier curve."""

    return _geometry.bezier_point(a, b, c, d, t)


def bezier_tangent(a: float, b: float, c: float, d: float, t: float) -> float:
    """Return the tangent value on a cubic Bézier curve."""

    return _geometry.bezier_tangent(a, b, c, d, t)


def spline_point(a: float, b: float, c: float, d: float, t: float) -> float:
    """Return one coordinate value on a spline curve."""

    return require_context().spline_point(a, b, c, d, t)


def spline_tangent(a: float, b: float, c: float, d: float, t: float) -> float:
    """Return the tangent value on a spline curve."""

    return require_context().spline_tangent(a, b, c, d, t)


def spline_property(name: str, value: float | None = None) -> float:
    """Get or set one spline drawing property by name."""

    return require_context().spline_property(name, value)


def spline_properties(**properties: float) -> dict[str, float]:
    """Set spline drawing properties and return current values."""

    return require_context().spline_properties(**properties)
