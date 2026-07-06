"""Global-mode pixel readback, mutation, export, and filter wrappers."""

from __future__ import annotations

from collections.abc import Buffer, Callable, Sequence
from pathlib import Path
from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake.api._context_call import context_call as _context_call
from gummysnake.api.current import require_context
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.core.pixels import FrameSaveInfo, PixelBuffer

type PixelValue = Color | tuple[int, int, int] | tuple[int, int, int, int] | Image


def load_pixels() -> PixelBuffer:
    """Read the canvas pixels into a mutable RGBA byte buffer.

    Returns:
        A ``PixelBuffer`` containing physical top-left-oriented RGBA bytes for the
        current canvas. Mutating this buffer marks dirty ranges that
        ``update_pixels()`` can upload efficiently.
    """

    return cast(PixelBuffer, _context_call("load_pixels"))


def load_pixel_bytes() -> bytes:
    """Read the current canvas pixels without creating a mutable buffer.

    Returns:
        Physical top-left-oriented RGBA bytes for the current canvas.
    """

    return cast(bytes, _context_call("load_pixel_bytes"))


def pixels() -> Sequence[int]:
    """Return the active pixel buffer, loading it first if needed.

    Returns:
        A sequence of physical RGBA byte values for the current canvas.
    """

    context = require_context()
    return cast(Sequence[int], context.pixels or context.load_pixels())


def pixel_array() -> list[list[tuple[int, int, int, int]]]:
    """Return canvas pixels as rows of RGBA color tuples.

    Returns:
        A list of rows, where each row contains ``(red, green, blue, alpha)``
        tuples for one logical pixel position.
    """

    return cast(list[list[tuple[int, int, int, int]]], _context_call("pixel_array"))


def update_pixels(pixels: Sequence[int] | Buffer | None = None) -> None:
    """Write pixel data back to the canvas.

    Args:
        pixels: Optional RGBA data to upload. If omitted, Gummy Snake uploads the
            dirty ranges from the buffer returned by ``load_pixels()``.
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
    """Read a pixel, a rectangular region, or the whole canvas.

    Args:
        x: Left pixel coordinate. Omit it to copy the whole canvas as an image.
        y: Top pixel coordinate. Required when ``x`` is provided.
        w: Width of the region to copy. Use with ``h`` to return an image region.
        h: Height of the region to copy. Use with ``w`` to return an image region.

    Returns:
        A ``Color`` for ``get(x, y)`` calls, or an ``Image`` for region and
        full-canvas copies.
    """

    return cast(Color | Image, _context_call("get", x, y, w, h))


def set(x: int, y: int, value: PixelValue) -> None:
    """Change one canvas pixel or draw an image starting at a pixel position.

    Args:
        x: Left pixel coordinate where the value should be written.
        y: Top pixel coordinate where the value should be written.
        value: Color tuple, ``Color``, or ``Image`` to place on the canvas.
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
    """Copy canvas pixels or draw a copied region back onto the canvas.

    Args:
        *args: Use no arguments to copy the full canvas, four integers to copy a
            region as an image, eight integers to copy a canvas region to another
            canvas region, or an ``Image`` plus eight integers to copy from an
            image onto the canvas.

    Returns:
        An ``Image`` when copying pixels out of the canvas, otherwise ``None``.
    """

    return cast(Image | None, _context_call("copy", *args))


def filter(mode: c.ImageFilter, value: float | None = None) -> None:
    """Apply an image filter to the current canvas.

    Args:
        mode: Filter constant such as ``gs.GRAY`` or ``gs.BLUR``.
        value: Optional strength or threshold used by filters that need one.
    """

    _context_call("filter", mode, value)


def save_canvas(path: str | Path, *, extension: str | None = None, overwrite: bool = True) -> Path:
    """Save the current canvas image to disk.

    Args:
        path: Destination file path.
        extension: Optional file extension to use instead of the suffix in
            ``path``.
        overwrite: Whether an existing file may be replaced.

    Returns:
        The final path that was written.
    """

    return cast(Path, _context_call("save_canvas", path, extension=extension, overwrite=overwrite))


def save_frames(
    path_pattern: str | Path,
    *,
    extension: str = "png",
    count: int = 1,
    duration: float | None = None,
    callback: Callable[[list[FrameSaveInfo]], None] | None = None,
    overwrite: bool = True,
) -> list[FrameSaveInfo]:
    """Save one or more canvas frames to image files.

    Args:
        path_pattern: File path or format string. Format strings may use
            ``{index}``, ``{frame}``, and ``{frame_count}`` placeholders.
        extension: File extension to use when ``path_pattern`` has no suffix.
        count: Number of frames to save.
        duration: Optional total animation duration in seconds. When omitted,
            frame duration is based on the sketch frame rate.
        callback: Optional function called with the list of saved-frame records.
        overwrite: Whether existing files may be replaced.

    Returns:
        A list of records describing each saved frame.
    """

    return cast(
        list[FrameSaveInfo],
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
    """Save repeated canvas captures as an animated GIF.

    Args:
        path: Destination GIF file path.
        count: Number of frames to capture.
        duration: Optional total animation duration in seconds.
        overwrite: Whether an existing file may be replaced.

    Returns:
        The final GIF path that was written.
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
