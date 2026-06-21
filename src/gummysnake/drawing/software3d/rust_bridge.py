"""Payload conversion for Rust-owned software 3D kernels."""

from __future__ import annotations

from typing import Any

import numpy as np

from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    Model3D,
    PerspectiveProjection,
    Projection3D,
    _model_rust_handle,
)
from gummysnake.exceptions import ArgumentValidationError


def _array_rows_as_tuples(array: np.ndarray) -> list[tuple[float, ...]]:
    return [tuple(float(value) for value in row) for row in array]


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
    model_transform: Matrix2D | None = None,
) -> list[dict[str, Any]]:
    from gummysnake.rust.canvas import require_canvas_runtime

    runtime = require_canvas_runtime()
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
    transform_payload: tuple[float, float, float, float, float, float] | None = None
    if model_transform is not None and model_transform != Matrix2D.identity():
        transform_payload = (
            model_transform.a,
            model_transform.b,
            model_transform.c,
            model_transform.d,
            model_transform.e,
            model_transform.f,
        )

    handle = _model_rust_handle(model)
    direct_project = getattr(runtime, "project_shade_model_handle", None)
    if handle is not None and direct_project is not None:
        try:
            return list(
                direct_project(
                    handle,
                    camera_payload,
                    projection_payload,
                    viewport_width,
                    viewport_height,
                    material_payload,
                    light_payloads,
                    normal_material,
                    cull_backfaces,
                    transform_payload,
                )
            )
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc

    if handle is not None:
        payload = handle.to_mesh_payload()
        source_meshes = [
            {
                "vertices": list(payload["vertices"]),
                "faces": [list(face) for face in payload["faces"]],
                "texcoords": list(payload.get("texcoords", ())),
            }
        ]
    else:
        source_meshes = [
            {
                "vertices": _array_rows_as_tuples(mesh.vertex_array()),
                "faces": [list(face) for face in mesh.faces],
                "texcoords": _array_rows_as_tuples(mesh.texcoord_array()),
            }
            for mesh in model.meshes
        ]

    if transform_payload is not None:
        import math

        a, b, c, d, e, f = transform_payload
        z_scale = (math.hypot(a, b) + math.hypot(c, d)) / 2.0
        linear = np.array(
            ((a, b, 0.0), (c, d, 0.0), (0.0, 0.0, z_scale)),
            dtype=np.float64,
        )
        offset = np.array((e, -f, 0.0), dtype=np.float64)
        meshes = []
        for mesh in source_meshes:
            vertices = np.asarray(mesh["vertices"], dtype=np.float64) @ linear + offset
            meshes.append(
                {
                    "vertices": _array_rows_as_tuples(vertices),
                    "faces": mesh["faces"],
                    "texcoords": mesh["texcoords"],
                }
            )
    else:
        meshes = source_meshes
    try:
        return list(
            runtime.project_shade_faces(
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
