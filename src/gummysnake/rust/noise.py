"""3D noise acceleration wrapper and Python reference implementation."""

from __future__ import annotations

import math

from gummysnake.rust.acceleration import acceleration_provider
from gummysnake.rust.validation import validate_noise_octaves


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
    """Return deterministic Perlin-style noise using Rust when available.
    
    Args:
        x: The x value. Expected type: `float`. Defaults to `0.0`.
        y: The y value. Expected type: `float`. Defaults to `0.0`.
        z: The z value. Expected type: `float`. Defaults to `0.0`.
        seed: The seed value. Expected type: `int`. Defaults to `0`.
        octaves: The octaves value. Expected type: `int`. Defaults to `4`.
        falloff: The falloff value. Expected type: `float`. Defaults to `0.5`.
        prefer_accelerated: The prefer accelerated value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        The return value. Type: `float`.
    """

    x = float(x)
    y = float(y)
    z = float(z)
    seed = int(seed)
    octaves = int(octaves)
    falloff = float(falloff)
    validate_noise_octaves(octaves)
    provider = acceleration_provider(prefer_accelerated)
    if provider is not None:
        return float(provider.noise3(x, y, z, seed, octaves, falloff))
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
    """Pure-Python reference implementation for the accelerated noise path.
    
    Args:
        x: The x value. Expected type: `float`. Defaults to `0.0`.
        y: The y value. Expected type: `float`. Defaults to `0.0`.
        z: The z value. Expected type: `float`. Defaults to `0.0`.
        seed: The seed value. Expected type: `int`. Defaults to `0`.
        octaves: The octaves value. Expected type: `int`. Defaults to `4`.
        falloff: The falloff value. Expected type: `float`. Defaults to `0.5`.
    
    Returns:
        The return value. Type: `float`.
    """

    x = float(x)
    y = float(y)
    z = float(z)
    seed = int(seed)
    octaves = int(octaves)
    falloff = float(falloff)
    validate_noise_octaves(octaves)

    total = 0.0
    amplitude = 1.0
    max_amplitude = 0.0
    frequency = 1.0
    for _ in range(octaves):
        total += perlin(x * frequency, y * frequency, z * frequency, seed) * amplitude
        max_amplitude += amplitude
        amplitude *= falloff
        frequency *= 2.0
    return total / max_amplitude if max_amplitude else 0.0


def perlin(x: float, y: float, z: float, seed: int) -> float:
    """Perlin.
    
    Args:
        x: The x value. Expected type: `float`.
        y: The y value. Expected type: `float`.
        z: The z value. Expected type: `float`.
        seed: The seed value. Expected type: `int`.
    
    Returns:
        The return value. Type: `float`.
    """
    x0 = math.floor(x)
    y0 = math.floor(y)
    z0 = math.floor(z)
    xf = x - x0
    yf = y - y0
    zf = z - z0
    u = fade(xf)
    v = fade(yf)
    w = fade(zf)

    dots = {}
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                grad = gradient(x0 + dx, y0 + dy, z0 + dz, seed)
                dots[(dx, dy, dz)] = grad[0] * (xf - dx) + grad[1] * (yf - dy) + grad[2] * (zf - dz)

    x00 = lerp(dots[(0, 0, 0)], dots[(1, 0, 0)], u)
    x10 = lerp(dots[(0, 1, 0)], dots[(1, 1, 0)], u)
    x01 = lerp(dots[(0, 0, 1)], dots[(1, 0, 1)], u)
    x11 = lerp(dots[(0, 1, 1)], dots[(1, 1, 1)], u)
    y0_value = lerp(x00, x10, v)
    y1_value = lerp(x01, x11, v)
    return (lerp(y0_value, y1_value, w) + 1.0) / 2.0


def gradient(x: int, y: int, z: int, seed: int) -> tuple[float, float, float]:
    """Gradient.
    
    Args:
        x: The x value. Expected type: `int`.
        y: The y value. Expected type: `int`.
        z: The z value. Expected type: `int`.
        seed: The seed value. Expected type: `int`.
    
    Returns:
        The return value. Type: `tuple[float, float, float]`.
    """
    hashed = hash_coords(x, y, z, seed)
    theta = (hashed & 0xFFFF) / 0xFFFF * math.tau
    phi = ((hashed >> 16) & 0xFFFF) / 0xFFFF * math.pi
    sin_phi = math.sin(phi)
    return math.cos(theta) * sin_phi, math.sin(theta) * sin_phi, math.cos(phi)


def hash_coords(x: int, y: int, z: int, seed: int) -> int:
    """Hash coords.
    
    Args:
        x: The x value. Expected type: `int`.
        y: The y value. Expected type: `int`.
        z: The z value. Expected type: `int`.
        seed: The seed value. Expected type: `int`.
    
    Returns:
        The return value. Type: `int`.
    """
    value = (seed & 0xFFFFFFFF) ^ (x * 374761393) ^ (y * 668265263) ^ (z * 2246822519)
    value = (value ^ (value >> 13)) * 1274126177
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def fade(t: float) -> float:
    """Fade.
    
    Args:
        t: The t value. Expected type: `float`.
    
    Returns:
        The return value. Type: `float`.
    """
    return t * t * t * (t * (t * 6 - 15) + 10)


def lerp(a: float, b: float, t: float) -> float:
    """Lerp.
    
    Args:
        a: The a value. Expected type: `float`.
        b: The b value. Expected type: `float`.
        t: The t value. Expected type: `float`.
    
    Returns:
        The return value. Type: `float`.
    """
    return a + (b - a) * t


__all__ = ["noise_3d", "noise_3d_python"]
