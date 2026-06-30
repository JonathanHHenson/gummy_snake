"""Rust bridge helpers: required canvas runtime plus optional acceleration hooks."""

from __future__ import annotations

from gummysnake.rust.canvas import (
    canvas_abi_version,
    canvas_gpu_status,
    canvas_health_check,
    canvas_import_error,
    is_canvas_runtime_available,
    require_canvas_runtime,
)
from gummysnake.rust.ecs import (
    ecs_abi_version,
    ecs_health_check,
    ecs_import_error,
    is_ecs_runtime_available,
    require_ecs_runtime,
)
from gummysnake.rust.noise import noise_3d_python
from gummysnake.rust.runtime import (
    acceleration_import_error,
    animated_noise_rgba,
    exclusion_blend_rgb,
    exclusion_blend_rgb_python,
    health_check,
    is_acceleration_available,
    noise_3d,
)

__all__ = [
    "acceleration_import_error",
    "animated_noise_rgba",
    "canvas_abi_version",
    "canvas_gpu_status",
    "canvas_health_check",
    "canvas_import_error",
    "ecs_abi_version",
    "ecs_health_check",
    "ecs_import_error",
    "exclusion_blend_rgb",
    "exclusion_blend_rgb_python",
    "health_check",
    "is_acceleration_available",
    "is_canvas_runtime_available",
    "is_ecs_runtime_available",
    "noise_3d",
    "noise_3d_python",
    "require_canvas_runtime",
    "require_ecs_runtime",
]
