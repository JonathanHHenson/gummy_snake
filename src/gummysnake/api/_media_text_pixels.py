"""Global-mode image, text, pixel, and compositing wrappers."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import Any, cast, overload

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.assets.image import Image
from gummysnake.assets.text import Font
from gummysnake.core.color import Color


def _context_call(name: str, *args: object, **kwargs: object) -> Any:
    return getattr(require_context(), name)(*args, **kwargs)


def image(*args: Any) -> None:
    _context_call("image", *args)


def text(value: object, x: float, y: float) -> None:
    _context_call("text", value, x, y)


def text_size(size: float | None = None) -> float:
    return cast(float, _context_call("text_size", size))


def text_font(font: Font | str | None = None) -> Font:
    return cast(Font, _context_call("text_font", font))


def text_style(style: c.TextStyle | None = None) -> c.TextStyle:
    return cast(c.TextStyle, _context_call("text_style", style))


def text_align(horizontal: c.TextAlign, vertical: c.TextAlign | None = None) -> None:
    _context_call("text_align", horizontal, vertical)


def text_leading(value: float | None = None) -> float:
    return cast(float, _context_call("text_leading", value))


def text_width(value: object) -> float:
    return cast(float, _context_call("text_width", value))


def text_ascent() -> float:
    return cast(float, _context_call("text_ascent"))


def text_descent() -> float:
    return cast(float, _context_call("text_descent"))


def font_ascent(font: Any | None = None) -> float:
    return cast(float, _context_call("font_ascent", font))


def font_descent(font: Any | None = None) -> float:
    return cast(float, _context_call("font_descent", font))


def font_width(value: object, font: Any | None = None) -> float:
    return cast(float, _context_call("font_width", value, font))


def font_bounds(
    value: object, x: float = 0.0, y: float = 0.0, font: Any | None = None
) -> dict[str, float]:
    return cast(dict[str, float], _context_call("font_bounds", value, x, y, font))


def text_bounds(value: object, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
    return cast(dict[str, float], _context_call("text_bounds", value, x, y))


def text_direction(value: str | None = None) -> str:
    return cast(str, _context_call("text_direction", value))


def text_wrap(value: str | None = None) -> str:
    return cast(str, _context_call("text_wrap", value))


def text_weight(value: int | None = None) -> int:
    return cast(int, _context_call("text_weight", value))


def text_property(name: str, value: Any | None = None) -> object:
    return _context_call("text_property", name, value)


def text_properties(**properties: Any) -> dict[str, object]:
    return cast(dict[str, object], _context_call("text_properties", **properties))


def describe(description: object, *, label: str = "canvas") -> dict[str, str]:
    return cast(dict[str, str], _context_call("describe", description, label=label))


def describe_element(name: object, description: object) -> dict[str, str]:
    return cast(dict[str, str], _context_call("describe_element", name, description))


def text_output() -> list[dict[str, str]]:
    return cast(list[dict[str, str]], _context_call("text_output"))


def grid_output() -> list[dict[str, str]]:
    return cast(list[dict[str, str]], _context_call("grid_output"))


def load_pixels() -> list[int]:
    return cast(list[int], _context_call("load_pixels"))


def load_pixel_bytes() -> bytes:
    return cast(bytes, _context_call("load_pixel_bytes"))


def pixels() -> Sequence[int]:
    context = require_context()
    return context.pixels or context.load_pixels()


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


def set(x: int, y: int, value: Any) -> None:
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


def blend_mode(mode: c.BlendMode) -> None:
    _context_call("blend_mode", mode)


def blend(*args: object) -> None:
    _context_call("blend", *args)


def erase() -> None:
    _context_call("erase")


def no_erase() -> None:
    _context_call("no_erase")
