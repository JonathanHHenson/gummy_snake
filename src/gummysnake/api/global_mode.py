"""Global-mode Gummy Snake-style API wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any, cast

from gummysnake import constants as c
from gummysnake.api._environment_input import (
    cursor,
    delta_time,
    display_height,
    display_width,
    focused,
    frame_count,
    frame_rate,
    get_target_frame_rate,
    is_looping,
    key,
    key_code,
    key_is_down,
    key_is_pressed,
    loop,
    millis,
    mouse_button,
    mouse_is_pressed,
    mouse_x,
    mouse_y,
    moved_x,
    moved_y,
    no_cursor,
    no_loop,
    pmouse_x,
    pmouse_y,
    redraw,
    touches,
    window_height,
    window_width,
)
from gummysnake.api._facades import current, keyboard, mouse
from gummysnake.api._lifecycle import draw, on, preload, run, setup, sketch
from gummysnake.api._media_text_pixels import (
    blend,
    blend_mode,
    copy,
    describe,
    describe_element,
    erase,
    filter,
    font_ascent,
    font_bounds,
    font_descent,
    font_width,
    get,
    grid_output,
    image,
    load_pixel_bytes,
    load_pixels,
    no_erase,
    pixel_array,
    pixels,
    save_canvas,
    set,
    text,
    text_align,
    text_ascent,
    text_bounds,
    text_descent,
    text_direction,
    text_font,
    text_leading,
    text_output,
    text_properties,
    text_property,
    text_size,
    text_style,
    text_weight,
    text_width,
    text_wrap,
    update_pixels,
)
from gummysnake.api.current import require_context
from gummysnake.assets.data import (
    create_writer,
    load_bytes,
    load_bytes_async,
    load_json,
    load_json_async,
    load_strings,
    load_strings_async,
    save_bytes,
    save_json,
    save_strings,
)
from gummysnake.assets.image import create_image, load_image, load_image_async
from gummysnake.assets.text import load_font, load_font_async
from gummysnake.core import geometry as _geometry
from gummysnake.core.data import shuffle
from gummysnake.core.math import (
    acos,
    asin,
    atan,
    atan2,
    constrain,
    cos,
    degrees,
    dist,
    fract,
    lerp,
    mag,
    map_value,
    max_value,
    min_value,
    norm,
    radians,
    sin,
    sq,
    tan,
)
from gummysnake.core.random import (
    noise,
    noise_detail,
    noise_seed,
    random,
    random_gaussian,
    random_seed,
)
from gummysnake.core.vector import create_vector

map = map_value

_UNSET = object()


def _context_call(name: str, *args: object, **kwargs: object) -> Any:
    return getattr(require_context(), name)(*args, **kwargs)


def create_canvas(
    width: int,
    height: int,
    renderer: c.RendererMode = c.P2D,
    *,
    pixel_density: float | None = None,
) -> None:
    require_context().create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)


def resize_canvas(width: int, height: int, *, pixel_density: float | None = None) -> None:
    require_context().resize_canvas(width, height, pixel_density=pixel_density)


def width() -> int:
    return require_context().width


def height() -> int:
    return require_context().height


def pixel_density(value: float | None = None) -> float:
    return require_context().pixel_density(value)


def display_density() -> float:
    return require_context().display_density()


def fast():
    return require_context().fast()


def enable_performance_diagnostics(enabled: bool = True, *, reset: bool = True) -> None:
    require_context().enable_performance_diagnostics(enabled, reset=reset)


def reset_performance_diagnostics() -> None:
    require_context().reset_performance_diagnostics()


def performance_diagnostics() -> dict[str, object]:
    return require_context().performance_diagnostics()


def renderer_performance_counters() -> dict[str, object]:
    return require_context().renderer_performance_counters()


def reset_renderer_performance_counters() -> None:
    require_context().reset_renderer_performance_counters()


def enable_frame_pacing_diagnostics(enabled: bool = True, *, reset: bool = True) -> None:
    require_context().enable_frame_pacing_diagnostics(enabled, reset=reset)


def frame_pacing_diagnostics() -> dict[str, object]:
    return require_context().frame_pacing_diagnostics()


def reset_frame_pacing_diagnostics() -> None:
    require_context().reset_frame_pacing_diagnostics()


def background(*args: object) -> None:
    require_context().background(*args)


def clear() -> None:
    require_context().clear()


def color(*args: object):
    return require_context().color(*args)


def color_mode(*args: Any) -> None:
    require_context().color_mode(*args)


def lerp_color(*args: Any):
    return require_context().lerp_color(*args)


def fill(*args: object) -> None:
    require_context().fill(*args)


def no_fill() -> None:
    require_context().no_fill()


def stroke(*args: object) -> None:
    require_context().stroke(*args)


def no_stroke() -> None:
    require_context().no_stroke()


def stroke_weight(weight: float) -> None:
    require_context().stroke_weight(weight)


def stroke_cap(cap: c.StrokeCap) -> None:
    require_context().stroke_cap(cap)


def stroke_join(join: c.StrokeJoin) -> None:
    require_context().stroke_join(join)


def rect_mode(mode: c.ShapeMode) -> None:
    require_context().rect_mode(mode)


def ellipse_mode(mode: c.ShapeMode) -> None:
    require_context().ellipse_mode(mode)


def image_mode(mode: c.ShapeMode) -> None:
    require_context().image_mode(mode)


def image_sampling(mode: c.ImageSampling | None = None) -> c.ImageSampling:
    return require_context().image_sampling(mode)


def smooth() -> None:
    require_context().smooth()


def no_smooth() -> None:
    require_context().no_smooth()


def point(x: object, y: float | None = None) -> None:
    px, py = _xy(x, y)
    require_context().point(px, py)


def line(*args: object) -> None:
    if len(args) == 2:
        x1, y1 = _xy(args[0])
        x2, y2 = _xy(args[1])
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
        points = [_xy(point) for point in coords]
        require_context().triangle(*(value for point in points for value in point))
        return
    if len(coords) == 6:
        require_context().triangle(*(float(cast(float, value)) for value in coords))
        return
    raise TypeError("triangle() requires three points or six coordinate values.")


def quad(*coords: object) -> None:
    if len(coords) == 4:
        points = [_xy(point) for point in coords]
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


def push() -> None:
    require_context().push()


def pop() -> None:
    require_context().pop()


@contextmanager
def pushed():
    context = require_context()
    context.push()
    try:
        yield
    finally:
        context.pop()


def _style_color_args(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(value)
    return (value,)


@contextmanager
def style(
    *,
    fill: object = _UNSET,
    stroke: object = _UNSET,
    stroke_weight: float | None = None,
    stroke_cap: c.StrokeCap | None = None,
    stroke_join: c.StrokeJoin | None = None,
    rect_mode: c.ShapeMode | None = None,
    ellipse_mode: c.ShapeMode | None = None,
    image_mode: c.ShapeMode | None = None,
    blend_mode: c.BlendMode | None = None,
):
    context = require_context()
    context.push()
    try:
        if fill is None:
            context.no_fill()
        elif fill is not _UNSET:
            context.fill(*_style_color_args(fill))
        if stroke is None:
            context.no_stroke()
        elif stroke is not _UNSET:
            context.stroke(*_style_color_args(stroke))
        if stroke_weight is not None:
            context.stroke_weight(stroke_weight)
        if stroke_cap is not None:
            context.stroke_cap(stroke_cap)
        if stroke_join is not None:
            context.stroke_join(stroke_join)
        if rect_mode is not None:
            context.rect_mode(rect_mode)
        if ellipse_mode is not None:
            context.ellipse_mode(ellipse_mode)
        if image_mode is not None:
            context.image_mode(image_mode)
        if blend_mode is not None:
            context.blend_mode(blend_mode)
        yield
    finally:
        context.pop()


def _xy(value: object, y: float | None = None) -> tuple[float, float]:
    if y is not None:
        return float(cast(float, value)), float(y)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if len(value) != 2:
            raise ValueError("Expected a 2-item coordinate sequence.")
        return float(value[0]), float(value[1])
    x = getattr(value, "x", None)
    point_y = getattr(value, "y", None)
    if x is not None and point_y is not None:
        return float(x), float(point_y)
    raise TypeError("Expected a vector-like object, 2-item sequence, or x/y pair.")


@contextmanager
def transform(
    *,
    translate: object = _UNSET,
    rotate: float | None = None,
    scale: object = _UNSET,
):
    context = require_context()
    context.push()
    try:
        if translate is not _UNSET:
            tx, ty = _xy(translate)
            context.translate(tx, ty)
        if rotate is not None:
            context.rotate(rotate)
        if scale is not _UNSET:
            if isinstance(scale, Sequence) and not isinstance(scale, str | bytes | bytearray):
                sx, sy = _xy(scale)
                context.scale(sx, sy)
            else:
                context.scale(float(cast(float, scale)))
        yield
    finally:
        context.pop()


def translate(x: float, y: float) -> None:
    require_context().translate(x, y)


def rotate(angle: float) -> None:
    require_context().rotate(angle)


def scale(x: float, y: float | None = None) -> None:
    require_context().scale(x, y)


def shear_x(angle: float) -> None:
    require_context().shear_x(angle)


def shear_y(angle: float) -> None:
    require_context().shear_y(angle)


def apply_matrix(*values: float) -> None:
    require_context().apply_matrix(*values)


def reset_matrix() -> None:
    require_context().reset_matrix()


def angle_mode(mode: c.AngleMode) -> None:
    require_context().angle_mode(mode)


__all__ = [
    "run",
    "sketch",
    "preload",
    "setup",
    "draw",
    "on",
    "current",
    "mouse",
    "keyboard",
    "create_canvas",
    "resize_canvas",
    "width",
    "height",
    "pixel_density",
    "display_density",
    "fast",
    "enable_performance_diagnostics",
    "reset_performance_diagnostics",
    "performance_diagnostics",
    "renderer_performance_counters",
    "reset_renderer_performance_counters",
    "enable_frame_pacing_diagnostics",
    "frame_pacing_diagnostics",
    "reset_frame_pacing_diagnostics",
    "background",
    "clear",
    "color",
    "color_mode",
    "lerp_color",
    "fill",
    "no_fill",
    "stroke",
    "no_stroke",
    "stroke_weight",
    "stroke_cap",
    "stroke_join",
    "rect_mode",
    "ellipse_mode",
    "image_mode",
    "image_sampling",
    "smooth",
    "no_smooth",
    "point",
    "line",
    "rect",
    "square",
    "ellipse",
    "circle",
    "triangle",
    "quad",
    "arc",
    "begin_shape",
    "vertex",
    "bezier_vertex",
    "quadratic_vertex",
    "spline_vertex",
    "end_shape",
    "bezier",
    "spline",
    "bezier_point",
    "bezier_tangent",
    "spline_point",
    "spline_tangent",
    "spline_property",
    "spline_properties",
    "push",
    "pop",
    "pushed",
    "style",
    "transform",
    "translate",
    "rotate",
    "scale",
    "shear_x",
    "shear_y",
    "apply_matrix",
    "reset_matrix",
    "angle_mode",
    "frame_rate",
    "frame_count",
    "delta_time",
    "millis",
    "no_loop",
    "loop",
    "redraw",
    "is_looping",
    "get_target_frame_rate",
    "window_width",
    "window_height",
    "display_width",
    "display_height",
    "focused",
    "cursor",
    "no_cursor",
    "mouse_x",
    "mouse_y",
    "pmouse_x",
    "pmouse_y",
    "moved_x",
    "moved_y",
    "mouse_is_pressed",
    "mouse_button",
    "key",
    "key_code",
    "key_is_pressed",
    "key_is_down",
    "touches",
    "image",
    "image_mode",
    "text",
    "text_size",
    "text_font",
    "text_style",
    "text_align",
    "text_leading",
    "text_width",
    "text_ascent",
    "text_descent",
    "font_ascent",
    "font_descent",
    "font_width",
    "font_bounds",
    "text_bounds",
    "text_direction",
    "text_wrap",
    "text_weight",
    "text_property",
    "text_properties",
    "describe",
    "describe_element",
    "text_output",
    "grid_output",
    "load_image",
    "load_image_async",
    "create_image",
    "load_font",
    "load_font_async",
    "load_bytes",
    "load_bytes_async",
    "save_bytes",
    "create_writer",
    "load_strings",
    "load_strings_async",
    "save_strings",
    "load_json",
    "load_json_async",
    "save_json",
    "load_pixels",
    "load_pixel_bytes",
    "update_pixels",
    "pixels",
    "pixel_array",
    "get",
    "set",
    "copy",
    "filter",
    "save_canvas",
    "create_vector",
    "map_value",
    "map",
    "constrain",
    "norm",
    "lerp",
    "dist",
    "mag",
    "radians",
    "degrees",
    "sin",
    "cos",
    "tan",
    "asin",
    "acos",
    "atan",
    "atan2",
    "sq",
    "fract",
    "min_value",
    "max_value",
    "random",
    "random_seed",
    "random_gaussian",
    "noise",
    "noise_seed",
    "noise_detail",
    "shuffle",
    "load_pixels",
    "load_pixel_bytes",
    "pixels",
    "pixel_array",
    "update_pixels",
    "save_canvas",
    "blend_mode",
    "blend",
    "erase",
    "no_erase",
]
