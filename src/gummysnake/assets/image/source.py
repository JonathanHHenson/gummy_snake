"""Image constructor source normalization."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast

from gummysnake.exceptions import ArgumentValidationError


class ImageSource(Protocol):
    """Protocol for image-like sources that expose dimensions and RGBA bytes."""

    width: int
    height: int

    def tobytes(self) -> bytes:
        """Return packed RGBA bytes for the image source."""
        ...


_ByteSourceCallback = Callable[[], bytes | bytearray | memoryview]


def coerce_image_source(
    width: int | ImageSource,
    height: int | None,
    pixels: bytes | bytearray | None,
) -> tuple[int, int, bytes]:
    """Normalize Image constructor inputs to width, height, and RGBA bytes."""
    if isinstance(width, int):
        if height is None:
            raise ArgumentValidationError("Image height is required.")
        image_width = int(width)
        image_height = int(height)
        if image_width <= 0 or image_height <= 0:
            raise ArgumentValidationError("Image dimensions must be positive.")
        return (
            image_width,
            image_height,
            bytes(pixels or b"\x00" * (image_width * image_height * 4)),
        )

    image_width = int(width.width)
    image_height = int(width.height)
    to_rgba_bytes: object = getattr(width, "to_rgba_bytes", None)
    tobytes: object = getattr(width, "tobytes", None)
    convert: object = getattr(width, "convert", None)
    source = convert("RGBA") if callable(convert) else width
    if callable(to_rgba_bytes):
        payload = bytes(cast(_ByteSourceCallback, to_rgba_bytes)())
    else:
        source_tobytes: object = getattr(source, "tobytes", None)
        if callable(source_tobytes):
            payload = bytes(cast(_ByteSourceCallback, source_tobytes)())
        elif callable(tobytes):
            payload = bytes(cast(_ByteSourceCallback, tobytes)())
        else:
            raise ArgumentValidationError("Image source must expose RGBA bytes.")
    return image_width, image_height, payload


__all__ = ["ImageSource", "coerce_image_source"]
