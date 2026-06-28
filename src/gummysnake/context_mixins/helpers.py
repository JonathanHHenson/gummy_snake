"""Internal helpers for SketchContext argument normalization."""

from __future__ import annotations

from collections.abc import Container, Sequence
from typing import Any, NamedTuple

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


class BlendArgs(NamedTuple):
    source_image: Image | None
    source_rect: tuple[int, int, int, int]
    dest_rect: tuple[int, int, int, int]
    mode: c.BlendMode


def coerce_int(value: Any) -> int:
    """Coerce int.
    
    Args:
        value: The value value. Expected type: `Any`.
    
    Returns:
        The return value. Type: `int`.
    """
    if isinstance(value, str | int | float):
        return int(value)
    raise ArgumentValidationError(
        f"Expected an integer-compatible value, got {type(value).__name__}."
    )


def rgba_bytes(value: Color | Sequence[int]) -> bytes:
    """Rgba bytes.
    
    Args:
        value: The value value. Expected type: `Color | Sequence[int]`.
    
    Returns:
        The return value. Type: `bytes`.
    """
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
    """Image draw args.
    
    Args:
        image: The image value. Expected type: `Image | CanvasImage`.
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        args: The positional arguments value. Expected type: `tuple[float, ...]`.
        image_mode: The image mode value. Expected type: `c.ShapeMode`.
    
    Returns:
        The return value. Type: `ImageDrawArgs`.
    """
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
    args: tuple[Any, ...],
    supported_modes: Container[c.BlendMode],
    *,
    backend_name: str,
) -> BlendArgs:
    """Blend args.
    
    Args:
        args: The positional arguments value. Expected type: `tuple[Any, ...]`.
        supported_modes: The supported modes value. Expected type: `Container[c.BlendMode]`.
        backend_name: The backend name value. Expected type: `str`.
    
    Returns:
        The return value. Type: `BlendArgs`.
    """
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
        (coerce_int(sx), coerce_int(sy), coerce_int(sw), coerce_int(sh)),
        (coerce_int(dx), coerce_int(dy), coerce_int(dw), coerce_int(dh)),
        mode,
    )


def copy_ints(values: tuple[Any, ...]) -> tuple[int, ...]:
    """Copy ints.
    
    Args:
        values: The values value. Expected type: `tuple[Any, ...]`.
    
    Returns:
        The return value. Type: `tuple[int, ...]`.
    """
    return tuple(int(value) for value in values)
