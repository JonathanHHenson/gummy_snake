"""Global-mode blend, erase, and compositing wrappers."""

from __future__ import annotations

from typing import overload

from gummysnake import constants as c
from gummysnake.api._context_call import context_call as _context_call
from gummysnake.assets.image import Image

type BlendArg = int | Image | c.BlendMode


def blend_mode(mode: c.BlendMode) -> None:
    """Set how new drawing commands combine with pixels already on the canvas.

    Args:
        mode: Blend mode constant such as ``gs.BLEND``, ``gs.ADD``, or
            ``gs.MULTIPLY``.
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
    """Blend a rectangular canvas region into another canvas region.

    Args:
        sx: Source region left coordinate.
        sy: Source region top coordinate.
        sw: Source region width.
        sh: Source region height.
        dx: Destination region left coordinate.
        dy: Destination region top coordinate.
        dw: Destination region width.
        dh: Destination region height.
        mode: Blend mode used to combine source and destination pixels.
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
    """Blend a rectangular image region onto the canvas.

    Args:
        image: Source image to copy from.
        sx: Source image region left coordinate.
        sy: Source image region top coordinate.
        sw: Source image region width.
        sh: Source image region height.
        dx: Destination canvas region left coordinate.
        dy: Destination canvas region top coordinate.
        dw: Destination canvas region width.
        dh: Destination canvas region height.
        mode: Blend mode used to combine source and destination pixels.
    """
    ...


def blend(*args: BlendArg) -> None:
    """Blend pixels from the canvas or an image using a blend mode.

    Args:
        *args: Either eight coordinates plus a blend mode, or an ``Image`` followed
            by eight coordinates plus a blend mode.
    """

    _context_call("blend", *args)


def erase() -> None:
    """Make following draw calls remove pixels instead of painting over them."""

    _context_call("erase")


def no_erase() -> None:
    """Return following draw calls to normal painting after ``erase()``."""

    _context_call("no_erase")


__all__ = [
    "blend_mode",
    "blend",
    "erase",
    "no_erase",
]
