"""Shared payload builders for Rust-backed software 3D operations."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import (
    Camera3D,
    FrustumProjection,
    Light3D,
    LightKind,
    Material3D,
    PerspectiveProjection,
    Projection3D,
    Vec3,
)

Matrix2DPayload = tuple[float, float, float, float, float, float]


def vec3_payload(value: Vec3) -> tuple[float, float, float]:
    """Vec3 payload.
    
    Args:
        value: The value value. Expected type: `Vec3`.
    
    Returns:
        The return value. Type: `tuple[float, float, float]`.
    """
    return (value.x, value.y, value.z)


def camera_payload(camera: Camera3D) -> dict[str, tuple[float, float, float]]:
    """Camera payload.
    
    Args:
        camera: The camera value. Expected type: `Camera3D`.
    
    Returns:
        The return value. Type: `dict[str, tuple[float, float, float]]`.
    """
    return {
        "eye": vec3_payload(camera.eye),
        "target": vec3_payload(camera.target),
        "up": vec3_payload(camera.up),
    }


def projection_payload(projection: Projection3D) -> dict[str, Any]:
    """Projection payload.
    
    Args:
        projection: The projection value. Expected type: `Projection3D`.
    
    Returns:
        The return value. Type: `dict[str, Any]`.
    """
    if isinstance(projection, PerspectiveProjection):
        return {
            "kind": "perspective",
            "fov_y": projection.fov_y,
            "aspect": projection.aspect,
            "near": projection.near,
            "far": projection.far,
        }
    if isinstance(projection, FrustumProjection):
        height = projection.top - projection.bottom
        width = projection.right - projection.left
        fov_y = math.degrees(2.0 * math.atan2(height / 2.0, projection.near))
        return {
            "kind": "perspective",
            "fov_y": fov_y,
            "aspect": width / height if height != 0 else None,
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
    """Projection cache key.
    
    Args:
        projection: The projection value. Expected type: `Projection3D`.
    
    Returns:
        The return value. Type: `tuple[object, ...]`.
    """
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
    """Material payload.
    
    Args:
        material: The material value. Expected type: `Material3D`.
    
    Returns:
        The return value. Type: `dict[str, Any]`.
    """
    return {
        "base_color": material.base_color,
        "emissive_color": material.emissive_color,
        "specular_color": material.specular_color,
        "shininess": material.shininess,
        "metalness": material.metalness,
    }


def light_payload(light: Light3D) -> dict[str, Any]:
    # The current Rust software 3D shader handles ambient/directional/point lights.
    # Spot and image lights are projected into compatible payloads while preserving
    # richer Python state for capability reporting and future native paths.
    """Light payload.
    
    Args:
        light: The light value. Expected type: `Light3D`.
    
    Returns:
        The return value. Type: `dict[str, Any]`.
    """
    payload_kind = "point" if light.kind in {LightKind.SPOT, LightKind.IMAGE} else light.kind.value
    return {
        "kind": payload_kind,
        "color": light.color,
        "intensity": light.intensity,
        "position": None if light.position is None else vec3_payload(light.position),
        "direction": None if light.direction is None else vec3_payload(light.direction),
        "angle": light.angle,
        "concentration": light.concentration,
        "falloff": light.falloff,
    }


def light_payloads(lights: Iterable[Light3D]) -> list[dict[str, Any]]:
    """Light payloads.
    
    Args:
        lights: The lights value. Expected type: `Iterable[Light3D]`.
    
    Returns:
        The return value. Type: `list[dict[str, Any]]`.
    """
    return [light_payload(light) for light in lights]


def lights_cache_key(lights: Iterable[Light3D]) -> tuple[object, ...]:
    """Lights cache key.
    
    Args:
        lights: The lights value. Expected type: `Iterable[Light3D]`.
    
    Returns:
        The return value. Type: `tuple[object, ...]`.
    """
    return tuple(
        (
            light.kind.value,
            light.color,
            light.intensity,
            None if light.position is None else vec3_payload(light.position),
            None if light.direction is None else vec3_payload(light.direction),
            light.angle,
            light.concentration,
            light.falloff,
            id(light.source) if light.source is not None else None,
        )
        for light in lights
    )


def model_transform_payload(transform: Matrix2D | None) -> Matrix2DPayload | None:
    """Model transform payload.
    
    Args:
        transform: The transform value. Expected type: `Matrix2D | None`.
    
    Returns:
        The return value. Type: `Matrix2DPayload | None`.
    """
    if transform is None or transform == Matrix2D.identity():
        return None
    return (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)


def model_transform_cache_key(transform: Matrix2D | None) -> Matrix2DPayload | None:
    """Model transform cache key.
    
    Args:
        transform: The transform value. Expected type: `Matrix2D | None`.
    
    Returns:
        The return value. Type: `Matrix2DPayload | None`.
    """
    return model_transform_payload(transform)
