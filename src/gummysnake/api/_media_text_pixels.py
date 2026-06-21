"""Global-mode image, text, pixel, and compositing wrappers."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict, Unpack, cast, overload

from gummysnake import constants as c
from gummysnake.api.current import require_context
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.assets.text import Font
from gummysnake.core.color import Color


class SupportsText(Protocol):
    def __str__(self) -> str: ...


class TextProperties(TypedDict, total=False):
    direction: str
    wrap: str
    weight: int


type PixelValue = Color | tuple[int, int, int] | tuple[int, int, int, int] | Image


def _context_call(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(require_context(), name)(*args, **kwargs)


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
    _context_call("image", *args)


def text(value: SupportsText, x: float, y: float) -> None:
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


def text_width(value: SupportsText) -> float:
    return cast(float, _context_call("text_width", value))


def text_ascent() -> float:
    return cast(float, _context_call("text_ascent"))


def text_descent() -> float:
    return cast(float, _context_call("text_descent"))


def font_ascent(font: Font | str | None = None) -> float:
    return cast(float, _context_call("font_ascent", font))


def font_descent(font: Font | str | None = None) -> float:
    return cast(float, _context_call("font_descent", font))


def font_width(value: SupportsText, font: Font | str | None = None) -> float:
    return cast(float, _context_call("font_width", value, font))


def font_bounds(
    value: SupportsText, x: float = 0.0, y: float = 0.0, font: Font | str | None = None
) -> dict[str, float]:
    return cast(dict[str, float], _context_call("font_bounds", value, x, y, font))


def text_bounds(value: SupportsText, x: float = 0.0, y: float = 0.0) -> dict[str, float]:
    return cast(dict[str, float], _context_call("text_bounds", value, x, y))


def text_direction(value: str | None = None) -> str:
    return cast(str, _context_call("text_direction", value))


def text_wrap(value: str | None = None) -> str:
    return cast(str, _context_call("text_wrap", value))


def text_weight(value: int | None = None) -> int:
    return cast(int, _context_call("text_weight", value))


@overload
def text_property(name: Literal["direction"], value: str | None = None) -> str: ...


@overload
def text_property(name: Literal["wrap"], value: str | None = None) -> str: ...


@overload
def text_property(name: Literal["weight"], value: int | None = None) -> int: ...


def text_property(name: str, value: str | int | None = None) -> str | int:
    return _context_call("text_property", name, value)


def text_properties(
    **properties: Unpack[TextProperties],
) -> dict[str, str | int | float | c.TextStyle]:
    return cast(
        dict[str, str | int | float | c.TextStyle], _context_call("text_properties", **properties)
    )


def describe(description: SupportsText, *, label: str = "canvas") -> dict[str, str]:
    return cast(dict[str, str], _context_call("describe", description, label=label))


def describe_element(name: SupportsText, description: SupportsText) -> dict[str, str]:
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


def blend_mode(mode: c.BlendMode) -> None:
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
    _context_call("blend", *args)


def erase() -> None:
    _context_call("erase")


def no_erase() -> None:
    _context_call("no_erase")
