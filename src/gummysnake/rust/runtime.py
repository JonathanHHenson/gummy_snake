"""Optional Rust acceleration hooks with Python fallbacks."""

from gummysnake.rust.acceleration import (
    accelerated as _accelerated,
)
from gummysnake.rust.acceleration import (
    acceleration_import_error,
)
from gummysnake.rust.animated import animated_noise_rgba_bytes
from gummysnake.rust.blend import exclusion_blend_rgb_bytes
from gummysnake.rust.canvas import (
    canvas_abi_version,
    canvas_gpu_status,
    canvas_health_check,
    canvas_import_error,
    is_canvas_runtime_available,
    require_canvas_runtime,
)
from gummysnake.rust.noise import noise_3d_python
from gummysnake.rust.validation import ByteBuffer, validate_noise_octaves, validate_same_length


def is_acceleration_available() -> bool:
    """Return whether the optional compiled extension is active."""

    return _accelerated is not None


def health_check() -> str:
    """Report which acceleration backend is currently serving wrapper calls."""

    if _accelerated is None:
        return "python-fallback"
    return str(_accelerated.health_check())


def noise_3d(
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    *,
    seed: int = 0,
    octaves: int = 4,
    falloff: float = 0.5,
    prefer_accelerated: bool = True,
) -> float:
    """Return deterministic Perlin-style noise using Rust when available."""

    x = float(x)
    y = float(y)
    z = float(z)
    seed = int(seed)
    octaves = int(octaves)
    falloff = float(falloff)
    validate_noise_octaves(octaves)
    if prefer_accelerated and _accelerated is not None:
        return float(_accelerated.noise3(x, y, z, seed, octaves, falloff))
    return noise_3d_python(x, y, z, seed=seed, octaves=octaves, falloff=falloff)


def exclusion_blend_rgb(
    base: ByteBuffer,
    overlay: ByteBuffer,
    *,
    prefer_accelerated: bool = True,
) -> bytes:
    """Blend packed RGB bytes with Gummy Snake's ``EXCLUSION`` formula."""

    base_bytes = bytes(base)
    overlay_bytes = bytes(overlay)
    validate_same_length(base_bytes, overlay_bytes)
    if prefer_accelerated and _accelerated is not None:
        return bytes(_accelerated.exclusion_blend_rgb(base_bytes, overlay_bytes))
    return exclusion_blend_rgb_bytes(base_bytes, overlay_bytes)


def exclusion_blend_rgb_python(base: ByteBuffer, overlay: ByteBuffer) -> bytes:
    """Pure-Python reference implementation for ``exclusion_blend_rgb``."""

    base_bytes = bytes(base)
    overlay_bytes = bytes(overlay)
    validate_same_length(base_bytes, overlay_bytes)
    return exclusion_blend_rgb_bytes(base_bytes, overlay_bytes)


def animated_noise_rgba(
    width: int,
    height: int,
    density: float,
    time: float,
    *,
    seed: int = 0,
    octaves: int = 4,
    falloff: float = 0.5,
    prefer_accelerated: bool = True,
) -> bytes:
    """Return RGBA pixels for the accelerated noise demo field."""

    width = int(width)
    height = int(height)
    density = float(density)
    time = float(time)
    seed = int(seed)
    octaves = int(octaves)
    falloff = float(falloff)
    validate_noise_octaves(octaves)
    if prefer_accelerated and _accelerated is not None:
        return bytes(
            _accelerated.animated_noise_rgba(width, height, density, time, seed, octaves, falloff)
        )
    return animated_noise_rgba_bytes(
        width,
        height,
        density,
        time,
        seed=seed,
        octaves=octaves,
        falloff=falloff,
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
    "is_canvas_runtime_available",
    "noise_3d",
    "noise_3d_python",
    "require_canvas_runtime",
]
