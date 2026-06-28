"""Python-native Gummy Snake-style data conversion and formatting helpers."""

from __future__ import annotations

from collections.abc import MutableSequence, Sequence

from gummysnake.core.random import shared_rng


def shuffle[T](values: Sequence[T], *, in_place: bool = False) -> list[T] | MutableSequence[T]:
    """Shuffle values using Gummy Snake's RNG controlled by ``random_seed()``.
    
    Args:
        values: The values value. Expected type: `Sequence[T]`.
        in_place: The in place value. Expected type: `bool`. Defaults to `False`.
    
    Returns:
        The return value. Type: `list[T] | MutableSequence[T]`.
    """

    if in_place:
        if not isinstance(values, MutableSequence):
            raise TypeError("shuffle(..., in_place=True) requires a mutable sequence.")
        shared_rng().shuffle(values)
        return values
    result = list(values)
    shared_rng().shuffle(result)
    return result


__all__ = ["shuffle"]
