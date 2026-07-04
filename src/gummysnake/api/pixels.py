"""Global-mode pixel readback, mutation, export, and filter wrappers."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake.api._context_call import context_call as _context_call
from gummysnake.api.current import require_context
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.core.pixels import PixelBuffer

type PixelValue = Color | tuple[int, int, int] | tuple[int, int, int, int] | Image


def load_pixels() -> PixelBuffer:
    """Load and return pixels.

    Args:
        None.

    Returns:
        The return value. Type: `PixelBuffer`.
    """
    return cast(PixelBuffer, _context_call("load_pixels"))


def load_pixel_bytes() -> bytes:
    """Load and return pixel bytes.

    Args:
        None.

    Returns:
        The return value. Type: `bytes`.
    """
    return cast(bytes, _context_call("load_pixel_bytes"))


def pixels() -> Sequence[int]:
    """Return pixels as a flat RGBA byte-value list.

    Args:
        None.

    Returns:
        The return value. Type: `Sequence[int]`.
    """
    context = require_context()
    return cast(Sequence[int], context.pixels or context.load_pixels())


def pixel_array() -> list[list[tuple[int, int, int, int]]]:
    """Return pixels as rows of RGBA tuples.

    Args:
        None.

    Returns:
        The return value. Type: `list[list[tuple[int, int, int, int]]]`.
    """
    return cast(list[list[tuple[int, int, int, int]]], _context_call("pixel_array"))


def update_pixels(pixels: Sequence[int] | Buffer | None = None) -> None:
    """Update pixels using the active pixels context.

    Args:
        pixels: The pixels value. Expected type: `Sequence[int] | Buffer | None`. Defaults to
            `None`.

    Returns:
        None.
    """
    _context_call("update_pixels", pixels)


@overload
def get() -> Image: ...


@overload
def get(x: int, y: int) -> Color: ...


@overload
def get(x: int, y: int, w: int, h: int) -> Image: ...


def get(
    x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None
) -> Color | Image:
    """Get using the active pixels context.

    Args:
        x: The x value. Expected type: `int | None`. Defaults to `None`.
        y: The y value. Expected type: `int | None`. Defaults to `None`.
        w: The w value. Expected type: `int | None`. Defaults to `None`.
        h: The h value. Expected type: `int | None`. Defaults to `None`.

    Returns:
        The return value. Type: `Color | Image`.
    """
    return cast(Color | Image, _context_call("get", x, y, w, h))


def set(x: int, y: int, value: PixelValue) -> None:
    """Set using the active pixels context.

    Args:
        x: The x value. Expected type: `int`.
        y: The y value. Expected type: `int`.
        value: The value value. Expected type: `PixelValue`.

    Returns:
        None.
    """
    _context_call("set", x, y, value)


@overload
def copy() -> Image: ...


@overload
def copy(sx: int, sy: int, sw: int, sh: int, /) -> Image: ...


@overload
def copy(sx: int, sy: int, sw: int, sh: int, dx: int, dy: int, dw: int, dh: int, /) -> None: ...


@overload
def copy(
    image: Image, sx: int, sy: int, sw: int, sh: int, dx: int, dy: int, dw: int, dh: int, /
) -> None: ...


def copy(*args: Any) -> Image | None:
    """Copy using the active pixels context.

    Args:
        *args: Additional positional arguments. Expected type: `Any`.

    Returns:
        The return value. Type: `Image | None`.
    """
    return cast(Image | None, _context_call("copy", *args))


def filter(mode: c.ImageFilter, value: float | None = None) -> None:
    """Filter using the active pixels context.

    Args:
        mode: The mode value. Expected type: `c.ImageFilter`.
        value: The value value. Expected type: `float | None`. Defaults to `None`.

    Returns:
        None.
    """
    _context_call("filter", mode, value)


def save_canvas(path: str | Path, *, extension: str | None = None, overwrite: bool = True) -> Path:
    """Save canvas data to the requested destination.

    Args:
        path: The path value. Expected type: `str | Path`.
        extension: The extension value. Expected type: `str | None`. Defaults to `None`.
        overwrite: The overwrite value. Expected type: `bool`. Defaults to `True`.

    Returns:
        The return value. Type: `Path`.
    """
    return cast(Path, _context_call("save_canvas", path, extension=extension, overwrite=overwrite))


def save_frames(
    path_pattern: str | Path,
    *,
    extension: str = "png",
    count: int = 1,
    duration: float | None = None,
    callback: Any = None,
    overwrite: bool = True,
) -> list[dict[str, object]]:
    """Save frames data to the requested destination.

    Args:
        path_pattern: The path pattern value. Expected type: `str | Path`.
        extension: The extension value. Expected type: `str`. Defaults to `'png'`.
        count: The count value. Expected type: `int`. Defaults to `1`.
        duration: The duration value. Expected type: `float | None`. Defaults to `None`.
        callback: The callback value. Expected type: `Any`. Defaults to `None`.
        overwrite: The overwrite value. Expected type: `bool`. Defaults to `True`.

    Returns:
        The return value. Type: `list[dict[str, object]]`.
    """
    return cast(
        list[dict[str, object]],
        _context_call(
            "save_frames",
            path_pattern,
            extension=extension,
            count=count,
            duration=duration,
            callback=callback,
            overwrite=overwrite,
        ),
    )


def save_gif(
    path: str | Path,
    *,
    count: int = 1,
    duration: float | None = None,
    overwrite: bool = True,
) -> Path:
    """Save gif data to the requested destination.

    Args:
        path: The path value. Expected type: `str | Path`.
        count: The count value. Expected type: `int`. Defaults to `1`.
        duration: The duration value. Expected type: `float | None`. Defaults to `None`.
        overwrite: The overwrite value. Expected type: `bool`. Defaults to `True`.

    Returns:
        The return value. Type: `Path`.
    """
    return cast(
        Path,
        _context_call("save_gif", path, count=count, duration=duration, overwrite=overwrite),
    )


__all__ = [
    "load_pixels",
    "load_pixel_bytes",
    "pixels",
    "pixel_array",
    "update_pixels",
    "get",
    "set",
    "copy",
    "filter",
    "save_canvas",
    "save_frames",
    "save_gif",
]
