"""Global-mode Gummy Snake-style API wrappers."""

from __future__ import annotations

import inspect
from collections.abc import Buffer, Callable, Sequence
from contextlib import contextmanager
from typing import Any, cast

from gummysnake import constants as c
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
from gummysnake.sketch import EVENT_CALLBACK_NAMES, FunctionSketch, SketchBuilder

map = map_value

_DECORATED_SKETCHES: dict[str, SketchBuilder] = {}
_UNSET = object()


class CurrentFacade:
    @property
    def width(self) -> int:
        return require_context().width

    @property
    def height(self) -> int:
        return require_context().height

    @property
    def frame_count(self) -> int:
        return require_context().frame_count

    @property
    def delta_time(self) -> float:
        return require_context().delta_time

    @property
    def pixel_density(self) -> float:
        return require_context().pixel_density()

    @property
    def display_density(self) -> float:
        return require_context().display_density()

    @property
    def is_looping(self) -> bool:
        return require_context().is_looping()


class MouseFacade:
    @property
    def x(self) -> float:
        return require_context().mouse_x

    @property
    def y(self) -> float:
        return require_context().mouse_y

    @property
    def previous_x(self) -> float:
        return require_context().pmouse_x

    @property
    def previous_y(self) -> float:
        return require_context().pmouse_y

    @property
    def moved_x(self) -> float:
        return require_context().moved_x

    @property
    def moved_y(self) -> float:
        return require_context().moved_y

    @property
    def is_pressed(self) -> bool:
        return require_context().mouse_is_pressed

    @property
    def button(self) -> str | None:
        return require_context().mouse_button

    @property
    def position(self):
        return create_vector(self.x, self.y)

    @property
    def previous_position(self):
        return create_vector(self.previous_x, self.previous_y)


class KeyboardFacade:
    @property
    def key(self) -> str | None:
        return require_context().key

    @property
    def code(self) -> int | None:
        return require_context().key_code

    @property
    def is_pressed(self) -> bool:
        return require_context().key_is_pressed

    def is_down(self, key_code: int | str) -> bool:
        if isinstance(key_code, str):
            if len(key_code) != 1:
                raise ValueError("keyboard.is_down() string keys must be one character.")
            context = require_context()
            return context.key_is_down(ord(key_code.lower())) or context.key_is_down(
                ord(key_code.upper())
            )
        return require_context().key_is_down(key_code)


current = CurrentFacade()
mouse = MouseFacade()
keyboard = KeyboardFacade()


def sketch(*, headless: bool | None = None) -> SketchBuilder:
    return SketchBuilder(headless=headless)


def _module_builder(module_name: str, *, headless: bool | None = None) -> SketchBuilder:
    builder = _DECORATED_SKETCHES.get(module_name)
    if builder is None:
        builder = SketchBuilder(headless=headless)
        _DECORATED_SKETCHES[module_name] = builder
    elif headless is not None:
        builder.headless = headless
    return builder


def _caller_module_name() -> str:
    current_frame = inspect.currentframe()
    caller_frame = current_frame.f_back.f_back if current_frame and current_frame.f_back else None
    caller_globals = caller_frame.f_globals if caller_frame is not None else {}
    return str(caller_globals.get("__name__", "__main__"))


def preload(callback: Callable[[], object]) -> Callable[[], object]:
    return _module_builder(_caller_module_name()).preload(callback)


def setup(callback: Callable[[], object]) -> Callable[[], object]:
    return _module_builder(_caller_module_name()).setup(callback)


def draw(callback: Callable[[], object]) -> Callable[[], object]:
    return _module_builder(_caller_module_name()).draw(callback)


def on(
    event_name: str | c.CallbackEventName | c.TouchEventName,
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    return _module_builder(_caller_module_name()).on(event_name)


def run(
    *,
    preload: Callable[[], object] | None = None,
    setup: Callable[[], object] | None = None,
    draw: Callable[[], object] | None = None,
    mouse_moved: Callable[..., None] | None = None,
    mouse_dragged: Callable[..., None] | None = None,
    mouse_pressed: Callable[..., None] | None = None,
    mouse_released: Callable[..., None] | None = None,
    mouse_clicked: Callable[..., None] | None = None,
    mouse_double_clicked: Callable[..., None] | None = None,
    mouse_wheel: Callable[..., None] | None = None,
    key_pressed: Callable[..., None] | None = None,
    key_released: Callable[..., None] | None = None,
    key_typed: Callable[..., None] | None = None,
    touch_started: Callable[..., None] | None = None,
    touch_moved: Callable[..., None] | None = None,
    touch_ended: Callable[..., None] | None = None,
    touch_cancelled: Callable[..., None] | None = None,
    headless: bool | None = None,
    max_frames: int | None = None,
):
    current_frame = inspect.currentframe()
    caller_frame = current_frame.f_back if current_frame is not None else None
    caller_globals = caller_frame.f_globals if caller_frame is not None else {}
    decorated = _DECORATED_SKETCHES.get(str(caller_globals.get("__name__", "__main__")))
    explicit_event_callbacks = {
        "mouse_moved": mouse_moved,
        "mouse_dragged": mouse_dragged,
        "mouse_pressed": mouse_pressed,
        "mouse_released": mouse_released,
        "mouse_clicked": mouse_clicked,
        "mouse_double_clicked": mouse_double_clicked,
        "mouse_wheel": mouse_wheel,
        "key_pressed": key_pressed,
        "key_released": key_released,
        "key_typed": key_typed,
        "touch_started": touch_started,
        "touch_moved": touch_moved,
        "touch_ended": touch_ended,
        "touch_cancelled": touch_cancelled,
    }
    event_callbacks: dict[str, Callable[..., object]] = {}
    decorated_event_callbacks = decorated.event_callbacks if decorated is not None else {}
    for name in EVENT_CALLBACK_NAMES:
        callback = (
            explicit_event_callbacks[name]
            or decorated_event_callbacks.get(name)
            or caller_globals.get(name)
        )
        if callable(callback):
            event_callbacks[name] = cast(Callable[..., None], callback)
    sketch = FunctionSketch(
        preload=preload
        or (decorated.preload_callback if decorated is not None else None)
        or caller_globals.get("preload"),
        setup=setup
        or (decorated.setup_callback if decorated is not None else None)
        or caller_globals.get("setup"),
        draw=draw
        or (decorated.draw_callback if decorated is not None else None)
        or caller_globals.get("draw"),
        event_callbacks=event_callbacks,
        headless=headless,
    )
    return sketch.run(max_frames=max_frames)


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


def frame_rate(value: float | None = None) -> float:
    return require_context().frame_rate(value)


def frame_count() -> int:
    return require_context().frame_count


def delta_time() -> float:
    return require_context().delta_time


def millis() -> float:
    return require_context().millis()


def no_loop() -> None:
    require_context().no_loop()


def loop() -> None:
    require_context().loop()


def redraw() -> None:
    require_context().redraw()


def is_looping() -> bool:
    return require_context().is_looping()


def get_target_frame_rate() -> float:
    return require_context().frame_rate()


def window_width() -> int:
    return require_context().width


def window_height() -> int:
    return require_context().height


def display_width() -> int:
    context = require_context()
    return round(context.width * context.display_density())


def display_height() -> int:
    context = require_context()
    return round(context.height * context.display_density())


def focused() -> bool:
    return True


def cursor(_kind: str | None = None) -> None:
    # Cursor presentation is backend-owned; this is a safe no-op for portable sketches.
    return None


def no_cursor() -> None:
    # Cursor presentation is backend-owned; this is a safe no-op for portable sketches.
    return None


def mouse_x() -> float:
    return require_context().state.input.mouse_x


def mouse_y() -> float:
    return require_context().state.input.mouse_y


def pmouse_x() -> float:
    return require_context().state.input.previous_mouse_x


def pmouse_y() -> float:
    return require_context().state.input.previous_mouse_y


def moved_x() -> float:
    return require_context().moved_x


def moved_y() -> float:
    return require_context().moved_y


def mouse_is_pressed() -> bool:
    return require_context().mouse_is_pressed


def mouse_button() -> str | None:
    return require_context().mouse_button


def key() -> str | None:
    return require_context().key


def key_code() -> int | None:
    return require_context().key_code


def key_is_pressed() -> bool:
    return require_context().key_is_pressed


def key_is_down(key_code: int) -> bool:
    return require_context().key_is_down(key_code)


def touches():
    return require_context().touches


def image(*args: Any) -> None:
    require_context().image(*args)


def text(value: object, x: float, y: float) -> None:
    require_context().text(value, x, y)


def text_size(size: float | None = None) -> float:
    return require_context().text_size(size)


def text_font(font: Any | None = None):
    return require_context().text_font(font)


def text_style(style: c.TextStyle | None = None) -> c.TextStyle:
    return require_context().text_style(style)


def text_align(horizontal: c.TextAlign, vertical: c.TextAlign | None = None) -> None:
    require_context().text_align(horizontal, vertical)


def text_leading(value: float | None = None) -> float:
    return require_context().text_leading(value)


def text_width(value: object) -> float:
    return require_context().text_width(value)


def text_ascent() -> float:
    return require_context().text_ascent()


def text_descent() -> float:
    return require_context().text_descent()


def font_ascent(font: Any | None = None) -> float:
    return require_context().font_ascent(font)


def font_descent(font: Any | None = None) -> float:
    return require_context().font_descent(font)


def font_width(value: object, font: Any | None = None) -> float:
    return require_context().font_width(value, font)


def font_bounds(
    value: object, x: float = 0.0, y: float = 0.0, font: Any | None = None
) -> dict[str, float]:
    return require_context().font_bounds(value, x, y, font)


def text_bounds(value: object, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
    return require_context().text_bounds(value, x, y)


def text_direction(value: str | None = None) -> str:
    return require_context().text_direction(value)


def text_wrap(value: str | None = None) -> str:
    return require_context().text_wrap(value)


def text_weight(value: int | None = None) -> int:
    return require_context().text_weight(value)


def text_property(name: str, value: object | None = None) -> object:
    return require_context().text_property(name, value)


def text_properties(**properties: object) -> dict[str, object]:
    return require_context().text_properties(**properties)


def describe(description: object, *, label: str = "canvas") -> dict[str, str]:
    return require_context().describe(description, label=label)


def describe_element(name: object, description: object) -> dict[str, str]:
    return require_context().describe_element(name, description)


def text_output() -> list[dict[str, str]]:
    return require_context().text_output()


def grid_output() -> list[dict[str, str]]:
    return require_context().grid_output()


def load_pixels() -> list[int]:
    return require_context().load_pixels()


def load_pixel_bytes() -> bytes:
    return require_context().load_pixel_bytes()


def pixels() -> Sequence[int]:
    context = require_context()
    return context.pixels or context.load_pixels()


def pixel_array():
    return require_context().pixel_array()


def update_pixels(pixels: Sequence[int] | Buffer | None = None) -> None:
    require_context().update_pixels(pixels)


def get(x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None):
    return require_context().get(x, y, w, h)


def set(x: int, y: int, value: Any) -> None:
    require_context().set(x, y, value)


def copy(*args: object):
    return require_context().copy(*args)


def filter(mode: c.ImageFilter, value: float | None = None) -> None:
    require_context().filter(mode, value)


def save_canvas(path: str, *, extension: str | None = None, overwrite: bool = True):
    return require_context().save_canvas(path, extension=extension, overwrite=overwrite)


def blend_mode(mode: c.BlendMode) -> None:
    require_context().blend_mode(mode)


def blend(*args: object) -> None:
    require_context().blend(*args)


def erase() -> None:
    require_context().erase()


def no_erase() -> None:
    require_context().no_erase()


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
