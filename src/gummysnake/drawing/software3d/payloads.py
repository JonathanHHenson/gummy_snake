"""Shared payload builders for Rust-backed software 3D operations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    PerspectiveProjection,
    Projection3D,
    Vec3,
)

Matrix2DPayload = tuple[float, float, float, float, float, float]


def vec3_payload(value: Vec3) -> tuple[float, float, float]:
    return (value.x, value.y, value.z)


def camera_payload(camera: Camera3D) -> dict[str, tuple[float, float, float]]:
    return {
        "eye": vec3_payload(camera.eye),
        "target": vec3_payload(camera.target),
        "up": vec3_payload(camera.up),
    }


def projection_payload(projection: Projection3D) -> dict[str, Any]:
    if isinstance(projection, PerspectiveProjection):
        return {
            "kind": "perspective",
            "fov_y": projection.fov_y,
            "aspect": projection.aspect,
            "near": projection.near,
            "far": projection.far,
        }
    return {
        "kind": "orthographic",
        "width": projection.width,
        "height": projection.height,
        "near": projection.near,
        "far": projection.far,
    }


def projection_cache_key(projection: Projection3D) -> tuple[object, ...]:
    payload = projection_payload(projection)
    if payload["kind"] == "perspective":
        return (
            "perspective",
            payload["fov_y"],
            payload["aspect"],
            payload["near"],
            payload["far"],
        )
    return (
        "orthographic",
        payload["width"],
        payload["height"],
        payload["near"],
        payload["far"],
    )


def material_payload(material: Material3D) -> dict[str, Any]:
    return {
        "base_color": material.base_color,
        "emissive_color": material.emissive_color,
        "specular_color": material.specular_color,
        "shininess": material.shininess,
    }


def light_payload(light: Light3D) -> dict[str, Any]:
    return {
        "kind": light.kind.value,
        "color": light.color,
        "intensity": light.intensity,
        "position": None if light.position is None else vec3_payload(light.position),
        "direction": None if light.direction is None else vec3_payload(light.direction),
    }


def light_payloads(lights: Iterable[Light3D]) -> list[dict[str, Any]]:
    return [light_payload(light) for light in lights]


def lights_cache_key(lights: Iterable[Light3D]) -> tuple[object, ...]:
    return tuple(
        (
            light.kind.value,
            light.color,
            light.intensity,
            None if light.position is None else vec3_payload(light.position),
            None if light.direction is None else vec3_payload(light.direction),
        )
        for light in lights
    )


def model_transform_payload(transform: Matrix2D | None) -> Matrix2DPayload | None:
    if transform is None or transform == Matrix2D.identity():
        return None
    return (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)


def model_transform_cache_key(transform: Matrix2D | None) -> Matrix2DPayload | None:
    return model_transform_payload(transform)
