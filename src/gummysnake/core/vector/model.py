"""Gummy Snake Vector-like mutable vector class."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast, overload

from gummysnake.core.vector.basic import VectorBasicMixin
from gummysnake.core.vector.common import Number, _components, register_vector_type
from gummysnake.core.vector.ops import VectorOpsMixin


@dataclass(slots=True)
class Vector(VectorBasicMixin, VectorOpsMixin):
    """Public Vector value for Gummy Snake vector features."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @overload
    def __init__(self, x: Number = 0, y: Number = 0, z: Number = 0) -> None: ...

    @overload
    def __init__(self, x: Iterable[Number], y: Number = 0, z: Number = 0) -> None: ...

    def __init__(self, x: Number | Iterable[Number] = 0, y: Number = 0, z: Number = 0) -> None:
        """Create a vector from numeric components or an iterable of components."""
        if not isinstance(x, int | float) and y == 0 and z == 0:
            self.x, self.y, self.z = _components(x)
        else:
            scalar_x = cast(Number, x)
            self.x = float(scalar_x)
            self.y = float(y)
            self.z = float(z)


register_vector_type(Vector)


@overload
def create_vector(x: Number = 0, y: Number = 0, z: Number = 0) -> Vector: ...


@overload
def create_vector(x: Iterable[Number], y: Number = 0, z: Number = 0) -> Vector: ...


def create_vector(x: Number | Iterable[Number] = 0, y: Number = 0, z: Number = 0) -> Vector:
    return Vector(x, y, z)


__all__ = ["Vector", "create_vector"]
