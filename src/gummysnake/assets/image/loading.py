"""Canvas-owned image abstraction and loading helpers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.assets.image.canvas import CanvasImage
from gummysnake.assets.image.core import Image
from gummysnake.exceptions import ArgumentValidationError


def load_image(path: str | Path) -> Image:
    image_path = resolve_asset_path(path)
    if not image_path.exists():
        raise ArgumentValidationError(f"Image file does not exist: {image_path!s}.")
    try:
        rust_image = CanvasImage.from_file(image_path)
    except Exception as exc:
        raise ArgumentValidationError(f"Could not load image {image_path!s}.") from exc
    return Image.from_rust_image(rust_image)


async def load_image_async(path: str | Path) -> Image:
    return load_image(path)


def create_image(width: int, height: int) -> Image:
    return Image(int(width), int(height))


__all__ = ["Image", "CanvasImage", "load_image", "load_image_async", "create_image"]
