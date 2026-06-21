"""Decoded media frame conversion helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from gummysnake.assets.image import Image
from gummysnake.exceptions import BackendCapabilityError


def frame_to_image(frame: Any) -> Image:
    shape = getattr(frame, "shape", None)
    if shape is None:
        raise BackendCapabilityError(
            "Decoded media frames could not be converted into Gummy Snake images."
        )
    height = int(shape[0])
    width = int(shape[1])
    if len(shape) == 2:
        return Image(width, height, convert_frame_bytes(frame, width, height, 1))
    if len(shape) != 3:
        raise BackendCapabilityError("Decoded media frames must be grayscale, BGR, or BGRA arrays.")

    channels = int(shape[2])
    if channels in {3, 4}:
        return Image(width, height, convert_frame_bytes(frame, width, height, channels))
    raise BackendCapabilityError("Decoded media frames must have 1, 3, or 4 channels.")


def convert_frame_bytes(frame: Any, width: int, height: int, channels: int) -> bytes:
    tobytes = getattr(frame, "tobytes", None)
    if not callable(tobytes):
        raise BackendCapabilityError(
            "Decoded media frames must expose contiguous bytes for Rust conversion."
        )
    from gummysnake.rust.canvas import require_canvas_runtime

    frame_bytes = bytes(cast(Callable[[], bytes], tobytes)())
    try:
        return bytes(
            require_canvas_runtime().media_frame_to_rgba(width, height, channels, frame_bytes)
        )
    except ValueError as exc:
        raise BackendCapabilityError(
            "Decoded media frames could not be converted to RGBA."
        ) from exc


__all__ = ["convert_frame_bytes", "frame_to_image"]
