"""Image rasterization helpers for shaded software 3D faces."""

from __future__ import annotations

import math
from typing import Any

from gummysnake.assets.image import Image as CanvasImage
from gummysnake.exceptions import ArgumentValidationError

from .types import ShadedFace


def rasterize_faces_image(
    faces: list[ShadedFace], *, viewport_width: float, viewport_height: float
) -> CanvasImage:
    """Rasterize faces image.
    
    Args:
        faces: The faces value. Expected type: `list[ShadedFace]`.
        viewport_width: The viewport width value. Expected type: `float`.
        viewport_height: The viewport height value. Expected type: `float`.
    
    Returns:
        The return value. Type: `CanvasImage`.
    """
    width = max(1, int(math.ceil(viewport_width)))
    height = max(1, int(math.ceil(viewport_height)))
    return _rasterize_faces_image_at(faces, width=width, height=height, offset_x=0, offset_y=0)


def rasterize_faces_image_region(
    faces: list[ShadedFace], *, viewport_width: float, viewport_height: float
) -> tuple[CanvasImage, int, int]:
    """Rasterize faces image region.
    
    Args:
        faces: The faces value. Expected type: `list[ShadedFace]`.
        viewport_width: The viewport width value. Expected type: `float`.
        viewport_height: The viewport height value. Expected type: `float`.
    
    Returns:
        The return value. Type: `tuple[CanvasImage, int, int]`.
    """
    if not faces:
        return CanvasImage(1, 1), 0, 0
    min_x = min(x for face in faces for x, _ in face.points)
    min_y = min(y for face in faces for _, y in face.points)
    max_x = max(x for face in faces for x, _ in face.points)
    max_y = max(y for face in faces for _, y in face.points)
    viewport_pixel_width = max(1, int(math.ceil(viewport_width)))
    viewport_pixel_height = max(1, int(math.ceil(viewport_height)))
    offset_x = max(0, min(viewport_pixel_width - 1, math.floor(min_x) - 1))
    offset_y = max(0, min(viewport_pixel_height - 1, math.floor(min_y) - 1))
    end_x = max(offset_x + 1, min(viewport_pixel_width, math.ceil(max_x) + 2))
    end_y = max(offset_y + 1, min(viewport_pixel_height, math.ceil(max_y) + 2))
    return (
        _rasterize_faces_image_at(
            faces,
            width=end_x - offset_x,
            height=end_y - offset_y,
            offset_x=offset_x,
            offset_y=offset_y,
        ),
        offset_x,
        offset_y,
    )


def rasterize_face_payload_region(
    faces: list[dict[str, Any]],
    *,
    viewport_width: float,
    viewport_height: float,
    texture: CanvasImage | None = None,
) -> tuple[CanvasImage, int, int]:
    """Rasterize face payload region.
    
    Args:
        faces: The faces value. Expected type: `list[dict[str, Any]]`.
        viewport_width: The viewport width value. Expected type: `float`.
        viewport_height: The viewport height value. Expected type: `float`.
        texture: The texture value. Expected type: `CanvasImage | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `tuple[CanvasImage, int, int]`.
    """
    if not faces:
        return CanvasImage(1, 1), 0, 0
    min_x = min(float(x) for face in faces for x, _ in face["points"])
    min_y = min(float(y) for face in faces for _, y in face["points"])
    max_x = max(float(x) for face in faces for x, _ in face["points"])
    max_y = max(float(y) for face in faces for _, y in face["points"])
    viewport_pixel_width = max(1, int(math.ceil(viewport_width)))
    viewport_pixel_height = max(1, int(math.ceil(viewport_height)))
    offset_x = max(0, min(viewport_pixel_width - 1, math.floor(min_x) - 1))
    offset_y = max(0, min(viewport_pixel_height - 1, math.floor(min_y) - 1))
    end_x = max(offset_x + 1, min(viewport_pixel_width, math.ceil(max_x) + 2))
    end_y = max(offset_y + 1, min(viewport_pixel_height, math.ceil(max_y) + 2))
    return (
        _rasterize_face_payload_at(
            faces,
            width=end_x - offset_x,
            height=end_y - offset_y,
            offset_x=offset_x,
            offset_y=offset_y,
            texture=texture,
        ),
        offset_x,
        offset_y,
    )


def _rasterize_faces_image_at(
    faces: list[ShadedFace], *, width: int, height: int, offset_x: int, offset_y: int
) -> CanvasImage:
    payload = []
    for face in faces:
        payload.append(
            {
                "points": [(x, y) for x, y in face.points],
                "color": face.color,
                "texcoords": None if face.texcoords is None else list(face.texcoords),
            }
        )
    texture = next((face.texture for face in faces if face.texture is not None), None)
    return _rasterize_face_payload_at(
        payload,
        width=width,
        height=height,
        offset_x=offset_x,
        offset_y=offset_y,
        texture=texture,
    )


def _rasterize_face_payload_at(
    faces: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    offset_x: int,
    offset_y: int,
    texture: CanvasImage | None,
) -> CanvasImage:
    from gummysnake.rust.canvas import require_canvas_runtime

    payload = []
    for face in faces:
        texture_payload = None
        if (
            texture is not None
            and face.get("texcoords") is not None
            and len(face["points"]) == len(face["texcoords"])
        ):
            texture_payload = {
                "width": texture.width,
                "height": texture.height,
                "pixels": texture.to_rgba_bytes(),
            }
        payload.append(
            {
                "points": [(float(x) - offset_x, float(y) - offset_y) for x, y in face["points"]],
                "color": face["color"],
                "texcoords": face.get("texcoords"),
                "texture": texture_payload,
            }
        )
    try:
        pixels = require_canvas_runtime().rasterize_faces_rgba(width, height, payload)
    except ValueError as exc:
        raise ArgumentValidationError(str(exc)) from exc
    return CanvasImage(width, height, pixels)
