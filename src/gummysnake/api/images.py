"""Global-mode image drawing and tint wrappers."""

from __future__ import annotations

from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.core.color import Color


def _context_call(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(require_context(), name)(*args, **kwargs)


@overload
def image(source: Image | CanvasImage, x: float, y: float, /) -> None:
    """Overload signature for image().
    
    Args:
        source: The source value. Expected type: `Image | CanvasImage`.
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
    
    Returns:
        None.
    """
    ...


@overload
def image(
    source: Image | CanvasImage, x: float, y: float, width: float, height: float, /
) -> None:
    """Overload signature for image().
    
    Args:
        source: The source value. Expected type: `Image | CanvasImage`.
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        width: The width value. Expected type: `float`.
        height: The height value. Expected type: `float`.
    
    Returns:
        None.
    """
    ...


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
) -> None:
    """Overload signature for image().
    
    Args:
        source: The source value. Expected type: `Image | CanvasImage`.
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        width: The width value. Expected type: `float`.
        height: The height value. Expected type: `float`.
        sx: The sx value. Expected type: `float`.
        sy: The sy value. Expected type: `float`.
        sw: The sw value. Expected type: `float`.
        sh: The sh value. Expected type: `float`.
    
    Returns:
        None.
    """
    ...


def image(*args: Any) -> None:
    """Image using the active images context.
    
    Args:
        *args: Additional positional arguments. Expected type: `Any`.
    
    Returns:
        None.
    """
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
def tint(value: Color | str, /) -> None:
    """Overload signature for tint().
    
    Args:
        value: The value value. Expected type: `Color | str`.
    
    Returns:
        None.
    """
    ...


@overload
def tint(gray: float, /) -> None:
    """Overload signature for tint().
    
    Args:
        gray: The gray value. Expected type: `float`.
    
    Returns:
        None.
    """
    ...


@overload
def tint(gray: float, alpha: float, /) -> None:
    """Overload signature for tint().
    
    Args:
        gray: The gray value. Expected type: `float`.
        alpha: The alpha value. Expected type: `float`.
    
    Returns:
        None.
    """
    ...


@overload
def tint(v1: float, v2: float, v3: float, /) -> None:
    """Overload signature for tint().
    
    Args:
        v1: The v1 value. Expected type: `float`.
        v2: The v2 value. Expected type: `float`.
        v3: The v3 value. Expected type: `float`.
    
    Returns:
        None.
    """
    ...


@overload
def tint(v1: float, v2: float, v3: float, alpha: float, /) -> None:
    """Overload signature for tint().
    
    Args:
        v1: The v1 value. Expected type: `float`.
        v2: The v2 value. Expected type: `float`.
        v3: The v3 value. Expected type: `float`.
        alpha: The alpha value. Expected type: `float`.
    
    Returns:
        None.
    """
    ...


def tint(*args: Any) -> None:
    """Tint using the active images context.
    
    Args:
        *args: Additional positional arguments. Expected type: `Any`.
    
    Returns:
        None.
    """
    _context_call("tint", *args)


def no_tint() -> None:
    """Disable tint for subsequent operations.
    
    Args:
        None.
    
    Returns:
        None.
    """
    _context_call("no_tint")


__all__ = [
    "image",
    "tint",
    "no_tint",
]
