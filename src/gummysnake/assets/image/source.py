"""Image constructor source normalization."""

from __future__ import annotations

from typing import Any, Protocol, cast

from gummysnake.exceptions import ArgumentValidationError


class ImageSource(Protocol):
    width: int
    height: int

    def tobytes(self) -> bytes: ...


def coerce_image_source(
    width: int | ImageSource,
    height: int | None,
    pixels: bytes | bytearray | None,
) -> tuple[int, int, bytes]:
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
    to_rgba_bytes: Any = getattr(width, "to_rgba_bytes", None)
    tobytes: Any = getattr(width, "tobytes", None)
    convert: Any = getattr(width, "convert", None)
    source = convert("RGBA") if callable(convert) else width
    if callable(to_rgba_bytes):
        payload = bytes(cast(Any, to_rgba_bytes)())
    else:
        source_tobytes: Any = getattr(source, "tobytes", None)
        if callable(source_tobytes):
            payload = bytes(cast(Any, source_tobytes)())
        elif callable(tobytes):
            payload = bytes(cast(Any, tobytes)())
        else:
            raise ArgumentValidationError("Image source must expose RGBA bytes.")
    return image_width, image_height, payload


__all__ = ["ImageSource", "coerce_image_source"]
