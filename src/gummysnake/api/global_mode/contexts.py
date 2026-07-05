"""Global-mode push/style/transform context helpers."""

from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from typing import Any, cast

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.api.global_mode.helpers import (
    _UNSET,
    ColorArgument,
    CoordinatePair,
    ScaleArgument,
    Unset,
    style_color_args,
    xy,
)


def push() -> None:
    require_context().push()


def pop() -> None:
    require_context().pop()


@contextmanager
def pushed() -> Generator[None]:
    context = require_context()
    context.push()
    try:
        yield
    finally:
        context.pop()


@contextmanager
def style(
    *,
    fill: ColorArgument | None | Unset = _UNSET,
    stroke: ColorArgument | None | Unset = _UNSET,
    stroke_weight: float | None = None,
    stroke_cap: c.StrokeCap | None = None,
    stroke_join: c.StrokeJoin | None = None,
    rect_mode: c.ShapeMode | None = None,
    ellipse_mode: c.ShapeMode | None = None,
    image_mode: c.ShapeMode | None = None,
    blend_mode: c.BlendMode | None = None,
) -> Generator[None]:
    context = require_context()
    context.push()
    try:
        if fill is None:
            context.no_fill()
        elif fill is not _UNSET:
            cast(Any, context).fill(*style_color_args(fill))
        if stroke is None:
            context.no_stroke()
        elif stroke is not _UNSET:
            cast(Any, context).stroke(*style_color_args(stroke))
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


@contextmanager
def transform(
    *,
    translate: CoordinatePair | Unset = _UNSET,
    rotate: float | None = None,
    scale: ScaleArgument | Unset = _UNSET,
) -> Generator[None]:
    context = require_context()
    context.push()
    try:
        if translate is not _UNSET:
            tx, ty = xy(translate)
            context.translate(tx, ty)
        if rotate is not None:
            context.rotate(rotate)
        if scale is not _UNSET:
            if isinstance(scale, Sequence) and not isinstance(scale, str | bytes | bytearray):
                sx, sy = xy(scale)
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


def apply_matrix(a: float, b: float, c: float, d: float, e: float, f: float) -> None:
    require_context().apply_matrix(a, b, c, d, e, f)


def reset_matrix() -> None:
    require_context().reset_matrix()


def angle_mode(mode: c.AngleMode) -> None:
    require_context().angle_mode(mode)
