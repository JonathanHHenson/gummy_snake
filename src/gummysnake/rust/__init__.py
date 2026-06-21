"""Optional Rust acceleration hooks with Python fallbacks."""

from __future__ import annotations

from gummysnake.rust.canvas import (
    canvas_abi_version,
    canvas_gpu_status,
    canvas_health_check,
    canvas_import_error,
    is_canvas_available,
    require_canvas_extension,
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
    "exclusion_blend_rgb",
    "exclusion_blend_rgb_python",
    "health_check",
    "is_acceleration_available",
    "is_canvas_available",
    "noise_3d",
    "noise_3d_python",
    "require_canvas_extension",
]
