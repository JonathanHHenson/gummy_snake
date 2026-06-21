"""Projection and shading facade for software 3D models."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, cast

from gummysnake.assets.image import Image as CanvasImage
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    Model3D,
    PerspectiveProjection,
    Projection3D,
    Vec3,
)
from gummysnake.exceptions import ArgumentValidationError

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
) -> list[ShadedFace]:
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
) -> tuple[object, ...]:
    if isinstance(projection, PerspectiveProjection):
        projection_key: tuple[object, ...] = (
            "perspective",
            projection.fov_y,
            projection.aspect,
            projection.near,
            projection.far,
        )
    else:
        projection_key = (
            "orthographic",
            projection.width,
            projection.height,
            projection.near,
            projection.far,
        )
    lights_key = tuple(
        (
            light.kind.value,
            light.color,
            light.intensity,
            None
            if light.position is None
            else (light.position.x, light.position.y, light.position.z),
            None
            if light.direction is None
            else (light.direction.x, light.direction.y, light.direction.z),
        )
        for light in lights
    )
    return (
        id(model) if cache_identity is None else cache_identity,
        camera,
        projection_key,
        viewport_width,
        viewport_height,
        material.base_color,
        material.emissive_color,
        material.specular_color,
        material.shininess,
        lights_key,
        normal_material,
        cull_backfaces,
    )


def texture_image(material: Material3D) -> CanvasImage | None:
    texture = material.texture
    if texture is None:
        return None
    source = texture.source
    return source if isinstance(source, CanvasImage) else None
