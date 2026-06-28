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
    """Push the current style and transform state.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().push()


def pop() -> None:
    """Restore the most recently pushed style and transform state.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().pop()


@contextmanager
def pushed() -> Generator[None]:
    """Temporarily push style and transform state in a context manager.
    
    Args:
        None.
    
    Returns:
        The return value. Type: `Generator[None]`.
    """
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
    """Temporarily override drawing style in a context manager.
    
    Args:
        fill: The fill value. Expected type: `ColorArgument | None | Unset`. Defaults to `_UNSET`.
        stroke: The stroke value. Expected type: `ColorArgument | None | Unset`. Defaults to
            `_UNSET`.
        stroke_weight: The stroke weight value. Expected type: `float | None`. Defaults to `None`.
        stroke_cap: The stroke cap value. Expected type: `c.StrokeCap | None`. Defaults to `None`.
        stroke_join: The stroke join value. Expected type: `c.StrokeJoin | None`. Defaults to
            `None`.
        rect_mode: The rect mode value. Expected type: `c.ShapeMode | None`. Defaults to `None`.
        ellipse_mode: The ellipse mode value. Expected type: `c.ShapeMode | None`. Defaults to
            `None`.
        image_mode: The image mode value. Expected type: `c.ShapeMode | None`. Defaults to `None`.
        blend_mode: The blend mode value. Expected type: `c.BlendMode | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Generator[None]`.
    """
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
    """Temporarily apply transform changes in a context manager.
    
    Args:
        translate: The translate value. Expected type: `CoordinatePair | Unset`. Defaults to
            `_UNSET`.
        rotate: The rotate value. Expected type: `float | None`. Defaults to `None`.
        scale: The scale value. Expected type: `ScaleArgument | Unset`. Defaults to `_UNSET`.
    
    Returns:
        The return value. Type: `Generator[None]`.
    """
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
    """Translate the active drawing transform.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().translate(x, y)


def rotate(angle: float) -> None:
    """Rotate the active drawing transform.
    
    Args:
        angle: The angle value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().rotate(angle)


def scale(x: float, y: float | None = None) -> None:
    """Scale the active drawing transform.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        None.
    """
    require_context().scale(x, y)


def shear_x(angle: float) -> None:
    """Shear the active transform along the x axis.
    
    Args:
        angle: The angle value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().shear_x(angle)


def shear_y(angle: float) -> None:
    """Shear the active transform along the y axis.
    
    Args:
        angle: The angle value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().shear_y(angle)


def apply_matrix(a: float, b: float, c: float, d: float, e: float, f: float) -> None:
    """Compose the active transform with a 2D affine matrix.
    
    Args:
        a: The a value. Expected type: `float`.
        b: The b value. Expected type: `float`.
        c: The c value. Expected type: `float`.
        d: The d value. Expected type: `float`.
        e: The e value. Expected type: `float`.
        f: The f value. Expected type: `float`.
    
    Returns:
        None.
    """
    require_context().apply_matrix(a, b, c, d, e, f)


def reset_matrix() -> None:
    """Reset the active drawing transform to identity.
    
    Args:
        None.
    
    Returns:
        None.
    """
    require_context().reset_matrix()


def angle_mode(mode: c.AngleMode) -> None:
    """Set whether angles are interpreted as radians or degrees.
    
    Args:
        mode: The mode value. Expected type: `c.AngleMode`.
    
    Returns:
        None.
    """
    require_context().angle_mode(mode)
