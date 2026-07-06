"""Internal helpers for SketchContext argument normalization."""

from __future__ import annotations

from collections.abc import Container, Sequence
from typing import NamedTuple, cast

from gummysnake import constants as c
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.core.color import Color
from gummysnake.core.geometry import resolve_rect
from gummysnake.exceptions import ArgumentValidationError


class ImageDrawArgs(NamedTuple):
    dx: float
    dy: float
    dw: float
    dh: float
    source: tuple[int, int, int, int] | None


type IntLike = str | int | float
type BlendArg = Image | IntLike | c.BlendMode


class BlendArgs(NamedTuple):
    source_image: Image | None
    source_rect: tuple[int, int, int, int]
    dest_rect: tuple[int, int, int, int]
    mode: c.BlendMode


def coerce_int(value: IntLike) -> int:
    if isinstance(value, str | int | float):
        return int(value)
    raise ArgumentValidationError(
        f"Expected an integer-compatible value, got {type(value).__name__}."
    )


def blend_coordinate(value: BlendArg) -> int:
    if isinstance(value, Image | c.BlendMode):
        raise ArgumentValidationError(
            "blend() rectangle values must be integer-compatible numbers."
        )
    return coerce_int(cast(IntLike, value))


def rgba_bytes(value: Color | Sequence[int]) -> bytes:
    rgba = value.to_tuple() if isinstance(value, Color) else tuple(value)
    if len(rgba) == 3:
        rgba = (*rgba, 255)
    if len(rgba) != 4:
        raise ArgumentValidationError("Pixel colors require three or four components.")
    return bytes(max(0, min(255, int(component))) for component in rgba)


def image_draw_args(
    image: Image | CanvasImage,
    x: float,
    y: float,
    args: tuple[float, ...],
    *,
    image_mode: c.ShapeMode,
) -> ImageDrawArgs:
    if not isinstance(image, Image | CanvasImage):
        raise ArgumentValidationError("image() requires a Gummy Snake Image or CanvasImage object.")
    source: tuple[int, int, int, int] | None
    if len(args) == 0:
        width = float(image.width)
        height = float(image.height)
        source = None
    elif len(args) == 2:
        width = float(args[0])
        height = float(args[1])
        source = None
    elif len(args) == 6:
        width = float(args[0])
        height = float(args[1])
        sx = float(args[2])
        sy = float(args[3])
        sw = float(args[4])
        sh = float(args[5])
        source = (int(sx), int(sy), int(sw), int(sh))
    else:
        raise ArgumentValidationError(
            "image() accepts image, x, y; image, x, y, w, h; or image, x, y, w, h, sx, sy, sw, sh."
        )
    dx, dy, dw, dh = resolve_rect(image_mode, float(x), float(y), width, height)
    return ImageDrawArgs(dx, dy, dw, dh, source)


def blend_args(
    args: tuple[BlendArg, ...],
    supported_modes: Container[c.BlendMode],
    *,
    backend_name: str,
) -> BlendArgs:
    if len(args) == 9:
        source_image = None
        sx, sy, sw, sh, dx, dy, dw, dh, mode = args
    elif len(args) == 10 and isinstance(args[0], Image):
        source_image = args[0]
        sx, sy, sw, sh, dx, dy, dw, dh, mode = args[1:]
    else:
        raise ArgumentValidationError(
            "blend() accepts sx, sy, sw, sh, dx, dy, dw, dh, mode or "
            "image, sx, sy, sw, sh, dx, dy, dw, dh, mode."
        )
    if not isinstance(mode, c.BlendMode):
        raise ArgumentValidationError("blend() mode must be a BlendMode enum value.")
    if mode not in supported_modes:
        raise ArgumentValidationError(
            f"Unsupported blend mode {mode!r} for backend {backend_name!r}."
        )
    return BlendArgs(
        source_image,
        (
            blend_coordinate(sx),
            blend_coordinate(sy),
            blend_coordinate(sw),
            blend_coordinate(sh),
        ),
        (
            blend_coordinate(dx),
            blend_coordinate(dy),
            blend_coordinate(dw),
            blend_coordinate(dh),
        ),
        mode,
    )


def copy_ints(values: tuple[IntLike, ...]) -> tuple[int, ...]:
    return tuple(int(value) for value in values)
