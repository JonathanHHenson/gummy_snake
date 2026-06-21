"""Global-mode shape and curve wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, cast, overload

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.api.global_mode.helpers import xy
from gummysnake.core import geometry as _geometry


class PointLike(Protocol):
    x: float
    y: float


CoordinatePair = Sequence[float] | PointLike


@overload
def point(position: CoordinatePair, /) -> None: ...


@overload
def point(x: float, y: float, /) -> None: ...


def point(x: Any, y: float | None = None) -> None:
    px, py = xy(x, y)
    require_context().point(px, py)


@overload
def line(start: CoordinatePair, end: CoordinatePair, /) -> None: ...


@overload
def line(x1: float, y1: float, x2: float, y2: float, /) -> None: ...


def line(*args: Any) -> None:
    if len(args) == 2:
        x1, y1 = xy(args[0])
        x2, y2 = xy(args[1])
    elif len(args) == 4:
        x1, y1, x2, y2 = (float(cast(float, value)) for value in args)
    else:
        raise TypeError("line() requires two points or four coordinate values.")
    require_context().line(x1, y1, x2, y2)


def rect(x: float, y: float, w: float, h: float | None = None) -> None:
    require_context().rect(x, y, w, h)


def square(x: float, y: float, size: float) -> None:
    require_context().square(x, y, size)


def ellipse(x: float, y: float, w: float, h: float | None = None) -> None:
    require_context().ellipse(x, y, w, h)


def circle(x: float, y: float, diameter: float) -> None:
    require_context().circle(x, y, diameter)


@overload
def triangle(p1: CoordinatePair, p2: CoordinatePair, p3: CoordinatePair, /) -> None: ...


@overload
def triangle(x1: float, y1: float, x2: float, y2: float, x3: float, y3: float, /) -> None: ...


def triangle(*coords: Any) -> None:
    if len(coords) == 3:
        points = [xy(point) for point in coords]
        require_context().triangle(*(value for point in points for value in point))
        return
    if len(coords) == 6:
        require_context().triangle(*(float(cast(float, value)) for value in coords))
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
    require_context().arc(x, y, width, height, start, stop, mode)


def begin_shape(kind: c.ShapeKind | None = None) -> None:
    require_context().begin_shape(kind)


def vertex(x: float, y: float) -> None:
    require_context().vertex(x, y)


def bezier_vertex(x2: float, y2: float, x3: float, y3: float, x4: float, y4: float) -> None:
    require_context().bezier_vertex(x2, y2, x3, y3, x4, y4)


def quadratic_vertex(cx: float, cy: float, x3: float, y3: float) -> None:
    require_context().quadratic_vertex(cx, cy, x3, y3)


def spline_vertex(x: float, y: float) -> None:
    require_context().spline_vertex(x, y)


def end_shape(mode: c.ArcMode = c.OPEN) -> None:
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
    require_context().spline(x1, y1, x2, y2, x3, y3, x4, y4)


def bezier_point(a: float, b: float, c: float, d: float, t: float) -> float:
    return _geometry.bezier_point(a, b, c, d, t)


def bezier_tangent(a: float, b: float, c: float, d: float, t: float) -> float:
    return _geometry.bezier_tangent(a, b, c, d, t)


def spline_point(a: float, b: float, c: float, d: float, t: float) -> float:
    return require_context().spline_point(a, b, c, d, t)


def spline_tangent(a: float, b: float, c: float, d: float, t: float) -> float:
    return require_context().spline_tangent(a, b, c, d, t)


def spline_property(name: str, value: float | None = None) -> float:
    return require_context().spline_property(name, value)


def spline_properties(**properties: float) -> dict[str, float]:
    return require_context().spline_properties(**properties)
