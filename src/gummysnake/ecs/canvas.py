"""Canvas drawing helpers for ECS logical-plan construction.

Import this module as ``from gummysnake.ecs import canvas as ca`` inside
Rust-executed ECS systems. These helpers record canvas draw actions into the ECS
logical plan; they are not runtime drawing aliases for Python systems or UDFs.
Use the normal ``gummysnake`` drawing API from explicit ``python=True`` ECS code.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from gummysnake.ecs.expression_tools import ExpressionInput
from gummysnake.exceptions import SystemPlanError


def _literal_arg(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _canvas_call(command: str, *args: ExpressionInput) -> None:
    from gummysnake.ecs.action_tools.building import active_build_session, append_action
    from gummysnake.ecs.actions import DefaultAction
    from gummysnake.ecs.expressions import ensure_expr

    if not active_build_session():
        raise SystemPlanError(
            "gummysnake.ecs.canvas functions can only be used while building an "
            "ECS logical plan. Use normal gummysnake drawing APIs such as "
            f"gs.{command}() inside @gs.draw callbacks or explicit python=True "
            "ECS systems/UDFs."
        )
    append_action(
        DefaultAction(
            "canvas",
            canvas_command=command,
            canvas_args=tuple(ensure_expr(_literal_arg(arg)) for arg in args),
        ),
        operation=f"ecs.canvas.{command}()",
    )


def background(*args: ExpressionInput) -> None:
    _canvas_call("background", *args)


def clear() -> None:
    _canvas_call("clear")


def fill(*args: ExpressionInput) -> None:
    _canvas_call("fill", *args)


def no_fill() -> None:
    _canvas_call("no_fill")


def stroke(*args: ExpressionInput) -> None:
    _canvas_call("stroke", *args)


def no_stroke() -> None:
    _canvas_call("no_stroke")


def stroke_weight(weight: ExpressionInput) -> None:
    _canvas_call("stroke_weight", weight)


def stroke_cap(cap: ExpressionInput) -> None:
    _canvas_call("stroke_cap", cap)


def stroke_join(join: ExpressionInput) -> None:
    _canvas_call("stroke_join", join)


def color_mode(
    mode: ExpressionInput,
    max1: ExpressionInput | None = None,
    max2: ExpressionInput | None = None,
    max3: ExpressionInput | None = None,
    max_alpha: ExpressionInput | None = None,
) -> None:
    args = tuple(arg for arg in (mode, max1, max2, max3, max_alpha) if arg is not None)
    _canvas_call("color_mode", *args)


def rect_mode(mode: ExpressionInput) -> None:
    _canvas_call("rect_mode", mode)


def ellipse_mode(mode: ExpressionInput) -> None:
    _canvas_call("ellipse_mode", mode)


def image_mode(mode: ExpressionInput) -> None:
    _canvas_call("image_mode", mode)


def image_sampling(mode: ExpressionInput) -> None:
    _canvas_call("image_sampling", mode)


def blend_mode(mode: ExpressionInput) -> None:
    _canvas_call("blend_mode", mode)


def erase() -> None:
    _canvas_call("erase")


def no_erase() -> None:
    _canvas_call("no_erase")


def tint(*args: ExpressionInput) -> None:
    _canvas_call("tint", *args)


def no_tint() -> None:
    _canvas_call("no_tint")


def smooth() -> None:
    _canvas_call("smooth")


def no_smooth() -> None:
    _canvas_call("no_smooth")


def point(x: ExpressionInput, y: ExpressionInput | None = None) -> None:
    if y is None:
        _canvas_call("point", x)
    else:
        _canvas_call("point", x, y)


def line(*args: ExpressionInput) -> None:
    _canvas_call("line", *args)


def rect(
    x: ExpressionInput, y: ExpressionInput, w: ExpressionInput, h: ExpressionInput | None = None
) -> None:
    if h is None:
        _canvas_call("rect", x, y, w)
    else:
        _canvas_call("rect", x, y, w, h)


def square(x: ExpressionInput, y: ExpressionInput, size: ExpressionInput) -> None:
    _canvas_call("square", x, y, size)


def ellipse(
    x: ExpressionInput,
    y: ExpressionInput,
    w: ExpressionInput,
    h: ExpressionInput | None = None,
) -> None:
    if h is None:
        _canvas_call("ellipse", x, y, w)
    else:
        _canvas_call("ellipse", x, y, w, h)


def circle(x: ExpressionInput, y: ExpressionInput, diameter: ExpressionInput) -> None:
    _canvas_call("circle", x, y, diameter)


def triangle(*args: ExpressionInput) -> None:
    _canvas_call("triangle", *args)


def quad(*args: ExpressionInput) -> None:
    _canvas_call("quad", *args)


def arc(
    x: ExpressionInput,
    y: ExpressionInput,
    width: ExpressionInput,
    height: ExpressionInput,
    start: ExpressionInput,
    stop: ExpressionInput,
    mode: ExpressionInput | None = None,
) -> None:
    if mode is None:
        _canvas_call("arc", x, y, width, height, start, stop)
    else:
        _canvas_call("arc", x, y, width, height, start, stop, mode)


def image(*args: Any) -> None:
    _canvas_call("image", *args)


def blend(*args: Any) -> None:
    _canvas_call("blend", *args)


def begin_shape(kind: ExpressionInput | None = None) -> None:
    if kind is None:
        _canvas_call("begin_shape")
    else:
        _canvas_call("begin_shape", kind)


def begin_contour() -> None:
    _canvas_call("begin_contour")


def end_contour() -> None:
    _canvas_call("end_contour")


def begin_clip() -> None:
    _canvas_call("begin_clip")


def clip() -> None:
    _canvas_call("clip")


def end_clip() -> None:
    _canvas_call("end_clip")


def vertex(x: ExpressionInput, y: ExpressionInput) -> None:
    _canvas_call("vertex", x, y)


def bezier_vertex(
    x2: ExpressionInput,
    y2: ExpressionInput,
    x3: ExpressionInput,
    y3: ExpressionInput,
    x4: ExpressionInput,
    y4: ExpressionInput,
) -> None:
    _canvas_call("bezier_vertex", x2, y2, x3, y3, x4, y4)


def quadratic_vertex(
    cx: ExpressionInput, cy: ExpressionInput, x3: ExpressionInput, y3: ExpressionInput
) -> None:
    _canvas_call("quadratic_vertex", cx, cy, x3, y3)


def spline_vertex(x: ExpressionInput, y: ExpressionInput) -> None:
    _canvas_call("spline_vertex", x, y)


def end_shape(mode: ExpressionInput | None = None) -> None:
    if mode is None:
        _canvas_call("end_shape")
    else:
        _canvas_call("end_shape", mode)


def bezier(*args: ExpressionInput) -> None:
    _canvas_call("bezier", *args)


def spline(*args: ExpressionInput) -> None:
    _canvas_call("spline", *args)


def push() -> None:
    _canvas_call("push")


def pop() -> None:
    _canvas_call("pop")


def translate(x: ExpressionInput, y: ExpressionInput) -> None:
    _canvas_call("translate", x, y)


def rotate(angle: ExpressionInput) -> None:
    _canvas_call("rotate", angle)


def scale(x: ExpressionInput, y: ExpressionInput | None = None) -> None:
    if y is None:
        _canvas_call("scale", x)
    else:
        _canvas_call("scale", x, y)


def shear_x(angle: ExpressionInput) -> None:
    _canvas_call("shear_x", angle)


def shear_y(angle: ExpressionInput) -> None:
    _canvas_call("shear_y", angle)


def apply_matrix(
    a: ExpressionInput,
    b: ExpressionInput,
    c: ExpressionInput,
    d: ExpressionInput,
    e: ExpressionInput,
    f: ExpressionInput,
) -> None:
    _canvas_call("apply_matrix", a, b, c, d, e, f)


def reset_matrix() -> None:
    _canvas_call("reset_matrix")


def angle_mode(mode: ExpressionInput) -> None:
    _canvas_call("angle_mode", mode)


def text_size(size: ExpressionInput) -> None:
    _canvas_call("text_size", size)


def text_font(font: Any) -> None:
    _canvas_call("text_font", font)


def text_style(style: ExpressionInput) -> None:
    _canvas_call("text_style", style)


def text_align(horizontal: ExpressionInput, vertical: ExpressionInput | None = None) -> None:
    if vertical is None:
        _canvas_call("text_align", horizontal)
    else:
        _canvas_call("text_align", horizontal, vertical)


def text_leading(value: ExpressionInput) -> None:
    _canvas_call("text_leading", value)


def text_direction(value: ExpressionInput) -> None:
    _canvas_call("text_direction", value)


def text_wrap(value: ExpressionInput) -> None:
    _canvas_call("text_wrap", value)


def text_weight(value: ExpressionInput) -> None:
    _canvas_call("text_weight", value)


def text(*args: ExpressionInput) -> None:
    _canvas_call("text", *args)


__all__ = [
    "angle_mode",
    "apply_matrix",
    "arc",
    "background",
    "begin_clip",
    "begin_contour",
    "begin_shape",
    "bezier",
    "bezier_vertex",
    "blend",
    "blend_mode",
    "circle",
    "clear",
    "clip",
    "color_mode",
    "ellipse",
    "ellipse_mode",
    "end_clip",
    "end_contour",
    "end_shape",
    "erase",
    "fill",
    "image",
    "image_mode",
    "image_sampling",
    "line",
    "no_erase",
    "no_fill",
    "no_smooth",
    "no_stroke",
    "no_tint",
    "point",
    "pop",
    "push",
    "quad",
    "quadratic_vertex",
    "rect",
    "rect_mode",
    "reset_matrix",
    "rotate",
    "scale",
    "shear_x",
    "shear_y",
    "smooth",
    "spline",
    "spline_vertex",
    "square",
    "stroke",
    "stroke_cap",
    "stroke_join",
    "stroke_weight",
    "text",
    "text_align",
    "text_direction",
    "text_font",
    "text_leading",
    "text_size",
    "text_style",
    "text_weight",
    "text_wrap",
    "tint",
    "translate",
    "triangle",
    "vertex",
]
