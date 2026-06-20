"""Optional Rust acceleration hooks with Python fallbacks.

The public package must remain usable when the compiled extension is not built.
Wrappers in this module call :mod:`p5.rust._accelerated` when it is
importable, and otherwise execute deterministic Python implementations.
"""

from __future__ import annotations

import math
from typing import Protocol, cast

from p5.rust.canvas import (
    canvas_abi_version,
    canvas_gpu_status,
    canvas_health_check,
    canvas_import_error,
    is_canvas_available,
    require_canvas_extension,
)

ByteBuffer = bytes | bytearray | memoryview


class _AcceleratedModule(Protocol):
    def health_check(self) -> str: ...

    def noise3(
        self,
        x: float,
        y: float,
        z: float,
        seed: int,
        octaves: int,
        falloff: float,
    ) -> float: ...

    def animated_noise_rgba(
        self,
        width: int,
        height: int,
        density: float,
        time: float,
        seed: int,
        octaves: int,
        falloff: float,
    ) -> bytes: ...

    def exclusion_blend_rgb(self, base: bytes, overlay: bytes) -> bytes: ...


_loaded_accelerated: _AcceleratedModule | None

try:
    from p5.rust import _accelerated as _loaded_accelerated
except ImportError as exc:
    _loaded_accelerated = None
    _ACCELERATION_IMPORT_ERROR: ImportError | None = exc
else:
    _ACCELERATION_IMPORT_ERROR = None

_accelerated = cast(_AcceleratedModule | None, _loaded_accelerated)


def is_acceleration_available() -> bool:
    """Return whether the optional compiled extension is active."""

    return _accelerated is not None


def acceleration_import_error() -> ImportError | None:
    """Return the import error that disabled acceleration, if any."""

    return _ACCELERATION_IMPORT_ERROR


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
    _validate_noise_octaves(octaves)
    if prefer_accelerated and _accelerated is not None:
        return float(_accelerated.noise3(x, y, z, seed, octaves, falloff))
    return noise_3d_python(x, y, z, seed=seed, octaves=octaves, falloff=falloff)


def noise_3d_python(
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    *,
    seed: int = 0,
    octaves: int = 4,
    falloff: float = 0.5,
) -> float:
    """Pure-Python reference implementation for the accelerated noise path."""

    x = float(x)
    y = float(y)
    z = float(z)
    seed = int(seed)
    octaves = int(octaves)
    falloff = float(falloff)
    _validate_noise_octaves(octaves)

    total = 0.0
    amplitude = 1.0
    max_amplitude = 0.0
    frequency = 1.0
    for _ in range(octaves):
        total += _perlin(x * frequency, y * frequency, z * frequency, seed) * amplitude
        max_amplitude += amplitude
        amplitude *= falloff
        frequency *= 2.0
    return total / max_amplitude if max_amplitude else 0.0


def exclusion_blend_rgb(
    base: ByteBuffer,
    overlay: ByteBuffer,
    *,
    prefer_accelerated: bool = True,
) -> bytes:
    """Blend packed RGB bytes with p5's ``EXCLUSION`` formula."""

    base_bytes = bytes(base)
    overlay_bytes = bytes(overlay)
    _validate_same_length(base_bytes, overlay_bytes)
    if prefer_accelerated and _accelerated is not None:
        return bytes(_accelerated.exclusion_blend_rgb(base_bytes, overlay_bytes))
    return _exclusion_blend_rgb_bytes(base_bytes, overlay_bytes)


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
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive.")
    if density <= 0 or not math.isfinite(density):
        raise ValueError("density must be positive.")
    _validate_noise_octaves(octaves)
    if prefer_accelerated and _accelerated is not None:
        return bytes(
            _accelerated.animated_noise_rgba(width, height, density, time, seed, octaves, falloff)
        )
    return _animated_noise_rgba_bytes(
        width,
        height,
        density,
        time,
        seed=seed,
        octaves=octaves,
        falloff=falloff,
    )


def exclusion_blend_rgb_python(base: ByteBuffer, overlay: ByteBuffer) -> bytes:
    """Pure-Python reference implementation for ``exclusion_blend_rgb``."""

    base_bytes = bytes(base)
    overlay_bytes = bytes(overlay)
    _validate_same_length(base_bytes, overlay_bytes)
    return _exclusion_blend_rgb_bytes(base_bytes, overlay_bytes)


def _animated_noise_rgba_bytes(
    width: int,
    height: int,
    density: float,
    time: float,
    *,
    seed: int,
    octaves: int,
    falloff: float,
) -> bytes:
    physical_width = max(1, int(round(width * density)))
    physical_height = max(1, int(round(height * density)))
    pixels = bytearray(physical_width * physical_height * 4)
    for y in range(physical_height):
        logical_y = y / density
        ridge = logical_y / max(1, height - 1)
        for x in range(physical_width):
            logical_x = x / density
            coarse = noise_3d_python(
                logical_x * 0.012,
                logical_y * 0.012,
                time,
                seed=seed,
                octaves=octaves,
                falloff=falloff,
            )
            detail = noise_3d_python(
                logical_x * 0.028 + 40,
                logical_y * 0.028 - 30,
                time * 1.7,
                seed=seed,
                octaves=octaves,
                falloff=falloff,
            )
            band = noise_3d_python(
                logical_x * 0.004,
                time * 0.55,
                logical_y * 0.01,
                seed=seed,
                octaves=octaves,
                falloff=falloff,
            )
            offset = (y * physical_width + x) * 4
            pixels[offset] = int(max(0, min(255, 18 + coarse * 70 + band * 30)))
            pixels[offset + 1] = int(max(0, min(255, 32 + detail * 110 + ridge * 40)))
            pixels[offset + 2] = int(max(0, min(255, 70 + coarse * 120 + detail * 45)))
            pixels[offset + 3] = 255
    return bytes(pixels)


def _validate_noise_octaves(octaves: int) -> None:
    if octaves < 1:
        msg = "octaves must be at least 1."
        raise ValueError(msg)


def _validate_same_length(base: bytes, overlay: bytes) -> None:
    if len(base) != len(overlay):
        msg = f"Buffers must have the same length, got {len(base)} and {len(overlay)}."
        raise ValueError(msg)


def _exclusion_blend_rgb_bytes(base: bytes, overlay: bytes) -> bytes:
    return bytes(
        max(0, min(255, b + o - 2 * b * o // 255)) for b, o in zip(base, overlay, strict=True)
    )


def _perlin(x: float, y: float, z: float, seed: int) -> float:
    x0 = math.floor(x)
    y0 = math.floor(y)
    z0 = math.floor(z)
    xf = x - x0
    yf = y - y0
    zf = z - z0
    u = _fade(xf)
    v = _fade(yf)
    w = _fade(zf)

    dots = {}
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                gradient = _gradient(x0 + dx, y0 + dy, z0 + dz, seed)
                dots[(dx, dy, dz)] = (
                    gradient[0] * (xf - dx) + gradient[1] * (yf - dy) + gradient[2] * (zf - dz)
                )

    x00 = _lerp(dots[(0, 0, 0)], dots[(1, 0, 0)], u)
    x10 = _lerp(dots[(0, 1, 0)], dots[(1, 1, 0)], u)
    x01 = _lerp(dots[(0, 0, 1)], dots[(1, 0, 1)], u)
    x11 = _lerp(dots[(0, 1, 1)], dots[(1, 1, 1)], u)
    y0_value = _lerp(x00, x10, v)
    y1_value = _lerp(x01, x11, v)
    return (_lerp(y0_value, y1_value, w) + 1.0) / 2.0


def _gradient(x: int, y: int, z: int, seed: int) -> tuple[float, float, float]:
    hashed = _hash(x, y, z, seed)
    theta = (hashed & 0xFFFF) / 0xFFFF * math.tau
    phi = ((hashed >> 16) & 0xFFFF) / 0xFFFF * math.pi
    sin_phi = math.sin(phi)
    return math.cos(theta) * sin_phi, math.sin(theta) * sin_phi, math.cos(phi)


def _hash(x: int, y: int, z: int, seed: int) -> int:
    value = (seed & 0xFFFFFFFF) ^ (x * 374761393) ^ (y * 668265263) ^ (z * 2246822519)
    value = (value ^ (value >> 13)) * 1274126177
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def _fade(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


__all__ = [
    "acceleration_import_error",
    "animated_noise_rgba",
    "exclusion_blend_rgb",
    "exclusion_blend_rgb_python",
    "canvas_abi_version",
    "canvas_gpu_status",
    "canvas_health_check",
    "canvas_import_error",
    "health_check",
    "is_acceleration_available",
    "is_canvas_available",
    "noise_3d",
    "noise_3d_python",
    "require_canvas_extension",
]
