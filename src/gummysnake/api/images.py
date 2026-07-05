"""Global-mode image drawing and tint wrappers."""

from __future__ import annotations

from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake.api._context_call import context_call as _context_call
from gummysnake.api.current import require_context
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.core.color import Color


@overload
def image(source: Image | CanvasImage, x: float, y: float, /) -> None: ...


@overload
def image(
    source: Image | CanvasImage, x: float, y: float, width: float, height: float, /
) -> None: ...


@overload
def image(
    source: Image | CanvasImage,
    x: float,
    y: float,
    width: float,
    height: float,
    sx: float,
    sy: float,
    sw: float,
    sh: float,
    /,
) -> None: ...


def image(*args: Any) -> None:
    if len(args) == 5 and isinstance(args[0], Image | CanvasImage):
        context = require_context()
        source = cast(Image | CanvasImage, args[0])
        x = float(cast(float, args[1]))
        y = float(cast(float, args[2]))
        width = float(cast(float, args[3]))
        height = float(cast(float, args[4]))
        if context.state.style.image_mode == c.CENTER:
            x -= width / 2.0
            y -= height / 2.0
        elif context.state.style.image_mode != c.CORNER:
            context.image(*args)
            return
        context._record_image_diagnostics(source)
        context.renderer.draw_image(
            source,
            x,
            y,
            width,
            height,
            context.state.style,
            context.state.transform.matrix,
            source=None,
        )
        return
    require_context().image(*args)


@overload
def tint(value: Color | str, /) -> None: ...


@overload
def tint(gray: float, /) -> None: ...


@overload
def tint(gray: float, alpha: float, /) -> None: ...


@overload
def tint(v1: float, v2: float, v3: float, /) -> None: ...


@overload
def tint(v1: float, v2: float, v3: float, alpha: float, /) -> None: ...


def tint(*args: Any) -> None:
    _context_call("tint", *args)


def no_tint() -> None:
    _context_call("no_tint")


__all__ = [
    "image",
    "tint",
    "no_tint",
]
