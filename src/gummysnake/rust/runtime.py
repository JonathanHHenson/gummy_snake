"""Facade for required canvas runtime and optional acceleration helpers."""

from __future__ import annotations

from gummysnake.rust.acceleration import (
    acceleration_import_error,
    health_check,
    is_acceleration_available,
)
from gummysnake.rust.animated import animated_noise_rgba
from gummysnake.rust.blend import exclusion_blend_rgb, exclusion_blend_rgb_python
from gummysnake.rust.canvas import (
    canvas_abi_version,
    canvas_gpu_status,
    canvas_health_check,
    canvas_import_error,
    is_canvas_runtime_available,
    require_canvas_runtime,
)
from gummysnake.rust.noise import noise_3d, noise_3d_python

__all__ = [
    "acceleration_import_error",
    "animated_noise_rgba",
    "canvas_abi_version",
    "canvas_gpu_status",
    "canvas_health_check",
    "canvas_import_error",
    "exclusion_blend_rgb",
    "exclusion_blend_rgb_python",
    "health_check",
    "is_acceleration_available",
    "is_canvas_runtime_available",
    "noise_3d",
    "noise_3d_python",
    "require_canvas_runtime",
]
