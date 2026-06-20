"""Python-native Gummy Snake-style data conversion and formatting helpers."""

from __future__ import annotations

import random as _random
from collections.abc import MutableSequence, Sequence


def shuffle[T](values: Sequence[T], *, in_place: bool = False) -> list[T] | MutableSequence[T]:
    """Shuffle values using Python's RNG.

    By default this returns a shuffled list, matching Python expectations and
    avoiding mutation surprises. Pass ``in_place=True`` for mutable sequences.
    """

    if in_place:
        if not isinstance(values, MutableSequence):
            raise TypeError("shuffle(..., in_place=True) requires a mutable sequence.")
        _random.shuffle(values)
        return values
    result = list(values)
    _random.shuffle(result)
    return result


__all__ = ["shuffle"]
