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
    _ensure_model_rust_handle,
)
from gummysnake.drawing.software3d.payloads import (
    camera_payload,
    light_payloads,
    material_payload,
    model_transform_payload,
    projection_payload,
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
    model_transform: Matrix2D | None = None,
) -> list[dict[str, Any]]:
    from gummysnake.rust.canvas import require_canvas_runtime

    runtime = require_canvas_runtime()
    camera_data = camera_payload(camera)
    projection_data = projection_payload(projection)
    material_data = material_payload(base_material)
    lights_data = light_payloads(lights)
    transform_payload = model_transform_payload(model_transform)

    handle = _ensure_model_rust_handle(model)
    if handle is None:
        raise ArgumentValidationError("Model3D requires Rust-backed mesh handles.")
    try:
        return list(
            runtime.project_shade_model_handle(
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
