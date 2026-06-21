"""Payload conversion for Rust-owned software 3D kernels."""

from __future__ import annotations

from typing import Any

from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    Model3D,
    PerspectiveProjection,
    Projection3D,
)
from gummysnake.exceptions import ArgumentValidationError


def rust_project_shade_faces(
    model: Model3D,
    camera: Camera3D,
    projection: Projection3D,
    *,
    viewport_width: float,
    viewport_height: float,
    base_material: Material3D,
    lights: tuple[Light3D, ...],
    normal_material: bool,
    cull_backfaces: bool,
) -> list[dict[str, Any]]:
    from gummysnake.rust.canvas import require_canvas_extension

    meshes = [
        {
            "vertices": [(vertex.x, vertex.y, vertex.z) for vertex in mesh.vertices],
            "faces": [list(face) for face in mesh.faces],
            "texcoords": list(mesh.texcoords),
        }
        for mesh in model.meshes
    ]
    camera_payload = {
        "eye": (camera.eye.x, camera.eye.y, camera.eye.z),
        "target": (camera.target.x, camera.target.y, camera.target.z),
        "up": (camera.up.x, camera.up.y, camera.up.z),
    }
    if isinstance(projection, PerspectiveProjection):
        projection_payload: dict[str, Any] = {
            "kind": "perspective",
            "fov_y": projection.fov_y,
            "aspect": projection.aspect,
            "near": projection.near,
            "far": projection.far,
        }
    else:
        projection_payload = {
            "kind": "orthographic",
            "width": projection.width,
            "height": projection.height,
            "near": projection.near,
            "far": projection.far,
        }
    material_payload = {
        "base_color": base_material.base_color,
        "emissive_color": base_material.emissive_color,
        "specular_color": base_material.specular_color,
        "shininess": base_material.shininess,
    }
    light_payloads = [
        {
            "kind": light.kind.value,
            "color": light.color,
            "intensity": light.intensity,
            "position": None
            if light.position is None
            else (light.position.x, light.position.y, light.position.z),
            "direction": None
            if light.direction is None
            else (light.direction.x, light.direction.y, light.direction.z),
        }
        for light in lights
    ]
    try:
        return list(
            require_canvas_extension().project_shade_faces(
                meshes,
                camera_payload,
                projection_payload,
                viewport_width,
                viewport_height,
                material_payload,
                light_payloads,
                normal_material,
                cull_backfaces,
            )
        )
    except ValueError as exc:
        raise ArgumentValidationError(str(exc)) from exc
