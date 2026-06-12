"""Global-mode p5-style API wrappers."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from p5_py.api.current import require_context
from p5_py.core import geometry as _geometry
from p5_py.sketch import FunctionSketch


def run(
    *,
    preload: Callable[[], None] | None = None,
    setup: Callable[[], None] | None = None,
    draw: Callable[[], None] | None = None,
    backend: str = "pyglet",
    max_frames: int | None = None,
):
    current_frame = inspect.currentframe()
    caller_frame = current_frame.f_back if current_frame is not None else None
    caller_globals = caller_frame.f_globals if caller_frame is not None else {}
    sketch = FunctionSketch(
        preload=preload or caller_globals.get("preload"),
        setup=setup or caller_globals.get("setup"),
        draw=draw or caller_globals.get("draw"),
        backend=backend,
    )
    return sketch.run(max_frames=max_frames)


def create_canvas(width: int, height: int, *, pixel_density: float = 1.0) -> None:
    require_context().create_canvas(width, height, pixel_density=pixel_density)


def resize_canvas(width: int, height: int, *, pixel_density: float | None = None) -> None:
    require_context().resize_canvas(width, height, pixel_density=pixel_density)


def width() -> int:
    return require_context().width


def height() -> int:
    return require_context().height


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


def rect_mode(mode: str) -> None:
    require_context().rect_mode(mode)


def ellipse_mode(mode: str) -> None:
    require_context().ellipse_mode(mode)


def point(x: float, y: float) -> None:
    require_context().point(x, y)


def line(x1: float, y1: float, x2: float, y2: float) -> None:
    require_context().line(x1, y1, x2, y2)


def rect(x: float, y: float, w: float, h: float | None = None) -> None:
    require_context().rect(x, y, w, h)


def square(x: float, y: float, size: float) -> None:
    require_context().square(x, y, size)


def ellipse(x: float, y: float, w: float, h: float | None = None) -> None:
    require_context().ellipse(x, y, w, h)


def circle(x: float, y: float, diameter: float) -> None:
    require_context().circle(x, y, diameter)


def triangle(*coords: float) -> None:
    require_context().triangle(*coords)


def quad(*coords: float) -> None:
    require_context().quad(*coords)


def arc(*args: Any) -> None:
    require_context().arc(*args)


def begin_shape(kind: str | None = None) -> None:
    require_context().begin_shape(kind)


def vertex(x: float, y: float) -> None:
    require_context().vertex(x, y)


def bezier_vertex(*coords: float) -> None:
    require_context().bezier_vertex(*coords)


def quadratic_vertex(*coords: float) -> None:
    require_context().quadratic_vertex(*coords)


def end_shape(mode: str = "open") -> None:
    require_context().end_shape(mode)


def bezier(*coords: float) -> None:
    require_context().bezier(*coords)


def bezier_point(a: float, b: float, c: float, d: float, t: float) -> float:
    return _geometry.bezier_point(a, b, c, d, t)


def bezier_tangent(a: float, b: float, c: float, d: float, t: float) -> float:
    return _geometry.bezier_tangent(a, b, c, d, t)


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


def angle_mode(mode: str) -> None:
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


def mouse_x() -> float:
    return require_context().state.input.mouse_x


def mouse_y() -> float:
    return require_context().state.input.mouse_y


def pmouse_x() -> float:
    return require_context().state.input.previous_mouse_x


def pmouse_y() -> float:
    return require_context().state.input.previous_mouse_y


def key_is_down(key_code: int) -> bool:
    return require_context().key_is_down(key_code)


def load_pixels() -> list[int]:
    return require_context().load_pixels()


def update_pixels(pixels: list[int]) -> None:
    require_context().update_pixels(pixels)


def save_canvas(path: str) -> None:
    require_context().save_canvas(path)


__all__ = [
    "run",
    "create_canvas",
    "resize_canvas",
    "width",
    "height",
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
    "rect_mode",
    "ellipse_mode",
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
    "end_shape",
    "bezier",
    "bezier_point",
    "bezier_tangent",
    "push",
    "pop",
    "pushed",
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
    "mouse_x",
    "mouse_y",
    "pmouse_x",
    "pmouse_y",
    "key_is_down",
    "load_pixels",
    "update_pixels",
    "save_canvas",
]
