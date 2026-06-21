"""Global-mode shape and curve wrappers."""

from __future__ import annotations

from typing import Any, cast

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.api.global_mode.helpers import xy
from gummysnake.core import geometry as _geometry


def point(x: object, y: float | None = None) -> None:
    px, py = xy(x, y)
    require_context().point(px, py)


def line(*args: object) -> None:
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


def triangle(*coords: object) -> None:
    if len(coords) == 3:
        points = [xy(point) for point in coords]
        require_context().triangle(*(value for point in points for value in point))
        return
    if len(coords) == 6:
        require_context().triangle(*(float(cast(float, value)) for value in coords))
        return
    raise TypeError("triangle() requires three points or six coordinate values.")


def quad(*coords: object) -> None:
    if len(coords) == 4:
        points = [xy(point) for point in coords]
        require_context().quad(*(value for point in points for value in point))
        return
    if len(coords) == 8:
        require_context().quad(*(float(cast(float, value)) for value in coords))
        return
    raise TypeError("quad() requires four points or eight coordinate values.")


def arc(*args: Any) -> None:
    require_context().arc(*args)


def begin_shape(kind: c.ShapeKind | None = None) -> None:
    require_context().begin_shape(kind)


def vertex(x: float, y: float) -> None:
    require_context().vertex(x, y)


def bezier_vertex(*coords: float) -> None:
    require_context().bezier_vertex(*coords)


def quadratic_vertex(*coords: float) -> None:
    require_context().quadratic_vertex(*coords)


def spline_vertex(x: float, y: float) -> None:
    require_context().spline_vertex(x, y)


def end_shape(mode: c.ArcMode = c.OPEN) -> None:
    require_context().end_shape(mode)


def bezier(*coords: float) -> None:
    require_context().bezier(*coords)


def spline(*coords: float) -> None:
    require_context().spline(*coords)


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
