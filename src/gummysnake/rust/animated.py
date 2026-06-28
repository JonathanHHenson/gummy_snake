"""Animated noise image generation wrappers."""

from __future__ import annotations

import math

from gummysnake.rust.acceleration import acceleration_provider
from gummysnake.rust.noise import noise_3d_python
from gummysnake.rust.validation import validate_noise_octaves


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
    """Return RGBA pixels for the accelerated noise demo field.
    
    Args:
        width: The width value. Expected type: `int`.
        height: The height value. Expected type: `int`.
        density: The density value. Expected type: `float`.
        time: The time value. Expected type: `float`.
        seed: The seed value. Expected type: `int`. Defaults to `0`.
        octaves: The octaves value. Expected type: `int`. Defaults to `4`.
        falloff: The falloff value. Expected type: `float`. Defaults to `0.5`.
        prefer_accelerated: The prefer accelerated value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        The return value. Type: `bytes`.
    """

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
    validate_noise_octaves(octaves)
    provider = acceleration_provider(prefer_accelerated)
    if provider is not None:
        return bytes(
            provider.animated_noise_rgba(width, height, density, time, seed, octaves, falloff)
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


def animated_noise_rgba_bytes(
    width: int,
    height: int,
    density: float,
    time: float,
    *,
    seed: int,
    octaves: int,
    falloff: float,
) -> bytes:
    """Animated noise rgba bytes.
    
    Args:
        width: The width value. Expected type: `int`.
        height: The height value. Expected type: `int`.
        density: The density value. Expected type: `float`.
        time: The time value. Expected type: `float`.
        seed: The seed value. Expected type: `int`.
        octaves: The octaves value. Expected type: `int`.
        falloff: The falloff value. Expected type: `float`.
    
    Returns:
        The return value. Type: `bytes`.
    """
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


__all__ = ["animated_noise_rgba"]
