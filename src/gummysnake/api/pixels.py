"""Global-mode pixel readback, mutation, export, and filter wrappers."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.assets.image import Image
from gummysnake.core.color import Color
from gummysnake.pixels import PixelBuffer


def _context_call(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(require_context(), name)(*args, **kwargs)


type PixelValue = Color | tuple[int, int, int] | tuple[int, int, int, int] | Image


def load_pixels() -> PixelBuffer:
    return cast(PixelBuffer, _context_call("load_pixels"))


def load_pixel_bytes() -> bytes:
    return cast(bytes, _context_call("load_pixel_bytes"))


def pixels() -> Sequence[int]:
    context = require_context()
    return cast(Sequence[int], context.pixels or context.load_pixels())


def pixel_array() -> list[list[tuple[int, int, int, int]]]:
    return cast(list[list[tuple[int, int, int, int]]], _context_call("pixel_array"))


def update_pixels(pixels: Sequence[int] | Buffer | None = None) -> None:
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
    return cast(Color | Image, _context_call("get", x, y, w, h))


def set(x: int, y: int, value: PixelValue) -> None:
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
    return cast(Image | None, _context_call("copy", *args))


def filter(mode: c.ImageFilter, value: float | None = None) -> None:
    _context_call("filter", mode, value)


def save_canvas(path: str | Path, *, extension: str | None = None, overwrite: bool = True) -> Path:
    return _context_call("save_canvas", path, extension=extension, overwrite=overwrite)


def save_frames(
    path_pattern: str | Path,
    *,
    extension: str = "png",
    count: int = 1,
    duration: float | None = None,
    callback: Any = None,
    overwrite: bool = True,
) -> list[dict[str, object]]:
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
