"""Global-mode blend, erase, and compositing wrappers."""

from __future__ import annotations

from typing import Any, overload

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.assets.image import Image


def _context_call(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(require_context(), name)(*args, **kwargs)


def blend_mode(mode: c.BlendMode) -> None:
    """Blend mode using the active compositing context.
    
    Args:
        mode: The mode value. Expected type: `c.BlendMode`.
    
    Returns:
        None.
    """
    _context_call("blend_mode", mode)


@overload
def blend(
    sx: int,
    sy: int,
    sw: int,
    sh: int,
    dx: int,
    dy: int,
    dw: int,
    dh: int,
    mode: c.BlendMode,
    /,
) -> None:
    """Overload signature for blend().
    
    Args:
        sx: The sx value. Expected type: `int`.
        sy: The sy value. Expected type: `int`.
        sw: The sw value. Expected type: `int`.
        sh: The sh value. Expected type: `int`.
        dx: The dx value. Expected type: `int`.
        dy: The dy value. Expected type: `int`.
        dw: The dw value. Expected type: `int`.
        dh: The dh value. Expected type: `int`.
        mode: The mode value. Expected type: `c.BlendMode`.
    
    Returns:
        None.
    """
    ...


@overload
def blend(
    image: Image,
    sx: int,
    sy: int,
    sw: int,
    sh: int,
    dx: int,
    dy: int,
    dw: int,
    dh: int,
    mode: c.BlendMode,
    /,
) -> None:
    """Overload signature for blend().
    
    Args:
        image: The image value. Expected type: `Image`.
        sx: The sx value. Expected type: `int`.
        sy: The sy value. Expected type: `int`.
        sw: The sw value. Expected type: `int`.
        sh: The sh value. Expected type: `int`.
        dx: The dx value. Expected type: `int`.
        dy: The dy value. Expected type: `int`.
        dw: The dw value. Expected type: `int`.
        dh: The dh value. Expected type: `int`.
        mode: The mode value. Expected type: `c.BlendMode`.
    
    Returns:
        None.
    """
    ...


def blend(*args: Any) -> None:
    """Blend using the active compositing context.
    
    Args:
        *args: Additional positional arguments. Expected type: `Any`.
    
    Returns:
        None.
    """
    _context_call("blend", *args)


def erase() -> None:
    """Erase using the active compositing context.
    
    Args:
        None.
    
    Returns:
        None.
    """
    _context_call("erase")


def no_erase() -> None:
    """Disable erase for subsequent operations.
    
    Args:
        None.
    
    Returns:
        None.
    """
    _context_call("no_erase")


__all__ = [
    "blend_mode",
    "blend",
    "erase",
    "no_erase",
]
