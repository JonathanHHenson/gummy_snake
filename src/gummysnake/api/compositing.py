"""Global-mode blend, erase, and compositing wrappers."""

from __future__ import annotations

from typing import Any, overload

from gummysnake import constants as c
from gummysnake.api._context_call import context_call as _context_call
from gummysnake.assets.image import Image


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
) -> None: ...


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
) -> None: ...


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
