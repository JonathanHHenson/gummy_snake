"""Python-native Gummy Snake-style data conversion and formatting helpers."""

from __future__ import annotations

from collections.abc import MutableSequence, Sequence
from typing import Literal, overload

from gummysnake.core.random import shared_rng


@overload
def shuffle[T](values: Sequence[T], *, in_place: Literal[False] = False) -> list[T]: ...


@overload
def shuffle[T](values: MutableSequence[T], *, in_place: Literal[True]) -> MutableSequence[T]: ...


def shuffle[T](values: Sequence[T], *, in_place: bool = False) -> list[T] | MutableSequence[T]:
    """Return a shuffled copy, or shuffle a mutable sequence in place."""
    if in_place:
        if not isinstance(values, MutableSequence):
            raise TypeError("shuffle(..., in_place=True) requires a mutable sequence.")
        shared_rng().shuffle(values)
        return values
    result = list(values)
    shared_rng().shuffle(result)
    return result


__all__ = ["shuffle"]
