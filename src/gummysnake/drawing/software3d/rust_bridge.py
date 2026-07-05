"""Payload conversion for Rust-owned software 3D kernels."""

from __future__ import annotations

from typing import Any

from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    Model3D,
    Projection3D,
    _model_rust_handle,
)
from gummysnake.drawing.software3d.payloads import (
    camera_payload,
    light_payloads,
    material_payload,
    model_transform_payload,
    projection_payload,
)
from gummysnake.exceptions import ArgumentValidationError


def _rows_as_tuples(rows: Any) -> list[tuple[float, ...]]:
    return [tuple(float(value) for value in row) for row in rows]


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
    camera_data = camera_payload(camera)
    projection_data = projection_payload(projection)
    material_data = material_payload(base_material)
    lights_data = light_payloads(lights)
    transform_payload = model_transform_payload(model_transform)

    handle = _model_rust_handle(model)
    direct_project = getattr(runtime, "project_shade_model_handle", None)
    if handle is not None and direct_project is not None:
        try:
            return list(
                direct_project(
                    handle,
                    camera_data,
                    projection_data,
                    viewport_width,
                    viewport_height,
                    material_data,
                    lights_data,
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
                "vertices": [(vertex.x, vertex.y, vertex.z) for vertex in mesh.vertices],
                "faces": [list(face) for face in mesh.faces],
                "texcoords": list(mesh.texcoords),
            }
            for mesh in model.meshes
        ]

    if transform_payload is not None:
        import math

        a, b, c, d, e, f = transform_payload
        z_scale = (math.hypot(a, b) + math.hypot(c, d)) / 2.0
        meshes = []
        for mesh in source_meshes:
            vertices = [
                (a * x + c * y + e, b * x + d * y - f, z * z_scale)
                for x, y, z in _rows_as_tuples(mesh["vertices"])
            ]
            meshes.append(
                {
                    "vertices": vertices,
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
                camera_data,
                projection_data,
                viewport_width,
                viewport_height,
                material_data,
                lights_data,
                normal_material,
                cull_backfaces,
            )
        )
    except ValueError as exc:
        raise ArgumentValidationError(str(exc)) from exc
