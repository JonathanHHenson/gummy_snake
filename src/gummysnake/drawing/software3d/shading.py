"""Projection and shading facade for software 3D models."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, cast

from gummysnake.assets.image import Image as CanvasImage
from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    Model3D,
    Projection3D,
    Vec3,
)
from gummysnake.exceptions import ArgumentValidationError

from .payloads import lights_cache_key, model_transform_cache_key, projection_cache_key
from .projection import validate_projection
from .rust_bridge import rust_project_shade_faces
from .types import ProjectedFace, RGBAFloat, ShadedFace

_SHADED_FACE_CACHE_SIZE = 256
_shaded_face_cache: OrderedDict[tuple[object, ...], list[dict[str, Any]]] = OrderedDict()


def shade_model_faces(
    model: Model3D,
    camera: Camera3D,
    projection: Projection3D,
    *,
    viewport_width: float,
    viewport_height: float,
    base_material: Material3D,
    lights: tuple[Light3D, ...],
    normal_material: bool = False,
    cull_backfaces: bool = True,
    cache_identity: object | None = None,
    model_transform: Matrix2D | None = None,
) -> list[ShadedFace]:
    """Shade model faces.
    
    Args:
        model: The model value. Expected type: `Model3D`.
        camera: The camera value. Expected type: `Camera3D`.
        projection: The projection value. Expected type: `Projection3D`.
        viewport_width: The viewport width value. Expected type: `float`.
        viewport_height: The viewport height value. Expected type: `float`.
        base_material: The base material value. Expected type: `Material3D`.
        lights: The lights value. Expected type: `tuple[Light3D, ...]`.
        normal_material: The normal material value. Expected type: `bool`. Defaults to `False`.
        cull_backfaces: The cull backfaces value. Expected type: `bool`. Defaults to `True`.
        cache_identity: The cache identity value. Expected type: `object | None`. Defaults to
            `None`.
        model_transform: The model transform value. Expected type: `Matrix2D | None`. Defaults to
            `None`.
    
    Returns:
        The return value. Type: `list[ShadedFace]`.
    """
    texture = texture_image(base_material)
    cache_key = shade_cache_key(
        model,
        camera,
        projection,
        viewport_width,
        viewport_height,
        base_material,
        lights,
        normal_material,
        cull_backfaces,
        cache_identity,
        model_transform,
    )
    payload = _shaded_face_cache.get(cache_key)
    if payload is not None:
        _shaded_face_cache.move_to_end(cache_key)
    else:
        payload = rust_project_shade_faces(
            model,
            camera,
            projection,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            base_material=base_material,
            lights=lights,
            normal_material=normal_material,
            cull_backfaces=cull_backfaces,
            model_transform=model_transform,
        )
        _shaded_face_cache[cache_key] = payload
        if len(_shaded_face_cache) > _SHADED_FACE_CACHE_SIZE:
            _ = _shaded_face_cache.popitem(last=False)
    return [
        shaded_face_from_payload(face, texture=None if normal_material else texture)
        for face in payload
    ]


def project_model_faces(
    model: Model3D,
    camera: Camera3D,
    projection: Projection3D,
    *,
    viewport_width: float,
    viewport_height: float,
    cull_backfaces: bool = True,
) -> list[ProjectedFace]:
    """Project model faces.
    
    Args:
        model: The model value. Expected type: `Model3D`.
        camera: The camera value. Expected type: `Camera3D`.
        projection: The projection value. Expected type: `Projection3D`.
        viewport_width: The viewport width value. Expected type: `float`.
        viewport_height: The viewport height value. Expected type: `float`.
        cull_backfaces: The cull backfaces value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        The return value. Type: `list[ProjectedFace]`.
    """
    if viewport_width <= 0 or viewport_height <= 0:
        raise ArgumentValidationError("viewport dimensions must be positive.")
    validate_projection(projection)
    payload = rust_project_shade_faces(
        model,
        camera,
        projection,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        base_material=Material3D(),
        lights=(),
        normal_material=False,
        cull_backfaces=cull_backfaces,
    )
    faces = []
    for face in payload:
        texcoords_payload = face.get("texcoords")
        faces.append(
            ProjectedFace(
                points=tuple((float(x), float(y)) for x, y in face["points"]),
                depth=float(face["depth"]),
                normal=Vec3(*cast(tuple[float, float, float], tuple(face["normal"]))),
                center=Vec3(*cast(tuple[float, float, float], tuple(face["center"]))),
                texcoords=None
                if texcoords_payload is None
                else tuple((float(u), float(v)) for u, v in texcoords_payload),
            )
        )
    return faces


def shaded_face_from_payload(face: dict[str, Any], *, texture: CanvasImage | None) -> ShadedFace:
    """Shaded face from payload.
    
    Args:
        face: The face value. Expected type: `dict[str, Any]`.
        texture: The texture value. Expected type: `CanvasImage | None`.
    
    Returns:
        The return value. Type: `ShadedFace`.
    """
    texcoords_payload = face.get("texcoords")
    return ShadedFace(
        points=tuple((float(x), float(y)) for x, y in face["points"]),
        color=cast(RGBAFloat, tuple(float(value) for value in face["color"])),
        depth=float(face["depth"]),
        texcoords=None
        if texcoords_payload is None
        else tuple((float(u), float(v)) for u, v in texcoords_payload),
        texture=texture,
    )


def shade_cache_key(
    model: Model3D,
    camera: Camera3D,
    projection: Projection3D,
    viewport_width: float,
    viewport_height: float,
    material: Material3D,
    lights: tuple[Light3D, ...],
    normal_material: bool,
    cull_backfaces: bool,
    cache_identity: object | None = None,
    model_transform: Matrix2D | None = None,
) -> tuple[object, ...]:
    """Shade cache key.
    
    Args:
        model: The model value. Expected type: `Model3D`.
        camera: The camera value. Expected type: `Camera3D`.
        projection: The projection value. Expected type: `Projection3D`.
        viewport_width: The viewport width value. Expected type: `float`.
        viewport_height: The viewport height value. Expected type: `float`.
        material: The material value. Expected type: `Material3D`.
        lights: The lights value. Expected type: `tuple[Light3D, ...]`.
        normal_material: The normal material value. Expected type: `bool`.
        cull_backfaces: The cull backfaces value. Expected type: `bool`.
        cache_identity: The cache identity value. Expected type: `object | None`. Defaults to
            `None`.
        model_transform: The model transform value. Expected type: `Matrix2D | None`. Defaults to
            `None`.
    
    Returns:
        The return value. Type: `tuple[object, ...]`.
    """
    return (
        id(model) if cache_identity is None else cache_identity,
        camera,
        projection_cache_key(projection),
        viewport_width,
        viewport_height,
        material.base_color,
        material.emissive_color,
        material.specular_color,
        material.shininess,
        material.metalness,
        lights_cache_key(lights),
        normal_material,
        cull_backfaces,
        model_transform_cache_key(model_transform),
    )


def texture_image(material: Material3D) -> CanvasImage | None:
    """Texture image.
    
    Args:
        material: The material value. Expected type: `Material3D`.
    
    Returns:
        The return value. Type: `CanvasImage | None`.
    """
    texture = material.texture
    if texture is None:
        return None
    source = texture.source
    return source if isinstance(source, CanvasImage) else None
