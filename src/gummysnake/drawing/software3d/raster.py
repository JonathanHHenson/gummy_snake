"""Image rasterization helpers for shaded software 3D faces."""

from __future__ import annotations

import math
from typing import cast

from gummysnake.assets.image import Image as CanvasImage
from gummysnake.exceptions import ArgumentValidationError

from .types import RGBAFloat, ScreenPoint, ShadedFace, UVCoord


def rasterize_faces_image(
    faces: list[ShadedFace], *, viewport_width: float, viewport_height: float
) -> CanvasImage:
    width = max(1, int(math.ceil(viewport_width)))
    height = max(1, int(math.ceil(viewport_height)))
    return _rasterize_faces_image_at(faces, width=width, height=height, offset_x=0, offset_y=0)


def rasterize_faces_image_region(
    faces: list[ShadedFace], *, viewport_width: float, viewport_height: float
) -> tuple[CanvasImage, int, int]:
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


def _rasterize_faces_image_at(
    faces: list[ShadedFace], *, width: int, height: int, offset_x: int, offset_y: int
) -> CanvasImage:
    from gummysnake.rust.canvas import require_canvas_runtime

    payload = []
    for face in faces:
        texture_payload = None
        if (
            face.texture is not None
            and face.texcoords is not None
            and len(face.points) == len(face.texcoords)
        ):
            texture_payload = {
                "width": face.texture.width,
                "height": face.texture.height,
                "pixels": face.texture.to_rgba_bytes(),
            }
        payload.append(
            {
                "points": [(x - offset_x, y - offset_y) for x, y in face.points],
                "color": face.color,
                "texcoords": None if face.texcoords is None else list(face.texcoords),
                "texture": texture_payload,
            }
        )
    try:
        pixels = require_canvas_runtime().rasterize_faces_rgba(width, height, payload)
    except ValueError as exc:
        raise ArgumentValidationError(str(exc)) from exc
    return CanvasImage(width, height, pixels)


def draw_textured_face(image: CanvasImage, face: ShadedFace) -> None:
    if face.texture is None or face.texcoords is None:
        return
    for triangle_points, triangle_texcoords in triangulated_face(face.points, face.texcoords):
        draw_textured_triangle(
            image, face.texture, triangle_points, triangle_texcoords, modulation=face.color
        )


def triangulated_face(points: tuple[ScreenPoint, ...], texcoords: tuple[UVCoord, ...]):
    for index in range(1, len(points) - 1):
        yield (
            (points[0], points[index], points[index + 1]),
            (texcoords[0], texcoords[index], texcoords[index + 1]),
        )


def draw_textured_triangle(
    target: CanvasImage,
    texture: CanvasImage,
    points: tuple[ScreenPoint, ScreenPoint, ScreenPoint],
    texcoords: tuple[UVCoord, UVCoord, UVCoord],
    *,
    modulation: RGBAFloat,
) -> None:
    (x1, y1), (x2, y2), (x3, y3) = points
    denominator = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if denominator == 0:
        return
    min_x = max(0, int(math.floor(min(x1, x2, x3))))
    max_x = min(target.width - 1, int(math.ceil(max(x1, x2, x3))))
    min_y = max(0, int(math.floor(min(y1, y2, y3))))
    max_y = min(target.height - 1, int(math.ceil(max(y1, y2, y3))))
    if min_x > max_x or min_y > max_y:
        return
    for py in range(min_y, max_y + 1):
        sample_y = py + 0.5
        for px in range(min_x, max_x + 1):
            sample_x = px + 0.5
            w1 = ((y2 - y3) * (sample_x - x3) + (x3 - x2) * (sample_y - y3)) / denominator
            w2 = ((y3 - y1) * (sample_x - x3) + (x1 - x3) * (sample_y - y3)) / denominator
            w3 = 1.0 - w1 - w2
            if w1 < -1e-6 or w2 < -1e-6 or w3 < -1e-6:
                continue
            u = w1 * texcoords[0][0] + w2 * texcoords[1][0] + w3 * texcoords[2][0]
            v = w1 * texcoords[0][1] + w2 * texcoords[1][1] + w3 * texcoords[2][1]
            tx = max(
                0, min(texture.width - 1, int(round(max(0.0, min(1.0, u)) * (texture.width - 1))))
            )
            ty = max(
                0,
                min(
                    texture.height - 1,
                    int(round((1.0 - max(0.0, min(1.0, v))) * (texture.height - 1))),
                ),
            )
            sampled = texture._pixel(tx, ty)
            shaded = tuple(int(round(sampled[index] * modulation[index])) for index in range(4))
            target._put_pixel(
                px, py, alpha_over(target._pixel(px, py), cast(tuple[int, int, int, int], shaded))
            )


def draw_polygon(
    target: CanvasImage, points: tuple[ScreenPoint, ...], color: tuple[int, int, int, int]
) -> None:
    if len(points) < 3:
        return
    min_x = max(0, int(math.floor(min(point[0] for point in points))))
    max_x = min(target.width - 1, int(math.ceil(max(point[0] for point in points))))
    min_y = max(0, int(math.floor(min(point[1] for point in points))))
    max_y = min(target.height - 1, int(math.ceil(max(point[1] for point in points))))
    for py in range(min_y, max_y + 1):
        for px in range(min_x, max_x + 1):
            if point_in_polygon(px + 0.5, py + 0.5, points):
                target._put_pixel(px, py, alpha_over(target._pixel(px, py), color))


def point_in_polygon(x: float, y: float, points: tuple[ScreenPoint, ...]) -> bool:
    inside = False
    previous = points[-1]
    for current in points:
        xi, yi = current
        xj, yj = previous
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        previous = current
    return inside


def alpha_over(
    destination: tuple[int, int, int, int], source: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    source_alpha = source[3] / 255.0
    if source_alpha <= 0.0:
        return destination
    destination_alpha = destination[3] / 255.0
    output_alpha = source_alpha + destination_alpha * (1.0 - source_alpha)
    if output_alpha <= 0.0:
        return (0, 0, 0, 0)
    blended = [
        (source[i] * source_alpha + destination[i] * destination_alpha * (1.0 - source_alpha))
        / output_alpha
        for i in range(3)
    ]
    return (
        int(round(blended[0])),
        int(round(blended[1])),
        int(round(blended[2])),
        int(round(output_alpha * 255.0)),
    )


def rgba_to_int(color: RGBAFloat) -> tuple[int, int, int, int]:
    return cast(
        tuple[int, int, int, int],
        tuple(int(round(max(0.0, min(1.0, component)) * 255.0)) for component in color),
    )
