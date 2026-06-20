"""Seedable Gummy Snake-style random and Perlin noise helpers."""

from __future__ import annotations

import random as _random
from collections.abc import Sequence
from typing import cast

from gummysnake.rust import noise_3d as _noise_3d

Number = int | float

_random_generator = _random.Random()
_noise_seed = 0
_noise_octaves = 4
_noise_falloff = 0.5


def random_seed(seed: int | float | str | bytes | bytearray | None) -> None:
    _random_generator.seed(seed)


def random(*args: object):
    if len(args) == 0:
        return _random_generator.random()
    if len(args) == 1:
        value = args[0]
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            if len(value) == 0:
                return None
            return _random_generator.choice(value)
        if not isinstance(value, int | float):
            raise TypeError("random(max) requires a numeric max value or a non-string sequence.")
        return _random_generator.random() * float(value)
    if len(args) == 2:
        if not all(isinstance(arg, int | float) for arg in args):
            raise TypeError("random(low, high) requires numeric bounds.")
        low, high = cast(tuple[Number, Number], args)
        low, high = float(low), float(high)
        return _random_generator.uniform(low, high)
    msg = "random() accepts zero arguments, a max value/list, or low and high values."
    raise TypeError(msg)


def random_gaussian(mean: Number = 0, sd: Number = 1) -> float:
    return _random_generator.gauss(float(mean), float(sd))


def noise_seed(seed: int) -> None:
    global _noise_seed
    _noise_seed = int(seed)


def noise_detail(octaves: int, falloff: Number | None = None) -> None:
    global _noise_octaves, _noise_falloff
    if octaves < 1:
        msg = "noise_detail() octave count must be at least 1."
        raise ValueError(msg)
    _noise_octaves = int(octaves)
    if falloff is not None:
        _noise_falloff = float(falloff)


def noise(x: Number = 0, y: Number = 0, z: Number = 0) -> float:
    return _noise_3d(
        float(x),
        float(y),
        float(z),
        seed=_noise_seed,
        octaves=_noise_octaves,
        falloff=_noise_falloff,
    )


__all__ = ["random", "random_seed", "random_gaussian", "noise", "noise_seed", "noise_detail"]
