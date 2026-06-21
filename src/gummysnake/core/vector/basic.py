"""Basic vector protocol and mutation helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any, cast

from gummysnake.core.vector.common import Number, _components


class VectorBasicMixin:
    x: float
    y: float
    z: float

    def __repr__(self) -> str:
        return f"Vector({self.x:g}, {self.y:g}, {self.z:g})"

    def __str__(self) -> str:
        return self.to_string()

    def __iter__(self):
        yield self.x
        yield self.y
        yield self.z

    def __len__(self) -> int:
        return 3

    def __getitem__(self, index: int) -> float:
        if index < 0:
            index += 3
        if index == 0:
            return self.x
        if index == 1:
            return self.y
        if index == 2:
            return self.z
        raise IndexError("Vector index must be 0, 1, or 2.")

    def __setitem__(self, index: int, value: Number) -> None:
        if index < 0:
            index += 3
        if index == 0:
            self.x = float(value)
            return
        if index == 1:
            self.y = float(value)
            return
        if index == 2:
            self.z = float(value)
            return
        raise IndexError("Vector index must be 0, 1, or 2.")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        return self.equals(other)

    def equals(self, other: object | Iterable[Number], *, abs_tol: float = 1e-09) -> bool:
        ox, oy, oz = _components(other)
        return (
            math.isclose(self.x, ox, abs_tol=abs_tol)
            and math.isclose(self.y, oy, abs_tol=abs_tol)
            and math.isclose(self.z, oz, abs_tol=abs_tol)
        )

    def copy(self):
        vector_type = cast("type[Any]", type(self))
        return vector_type(self.x, self.y, self.z)

    def set(
        self,
        value: object | Iterable[Number] | Number,
        y: Number | None = None,
        z: Number | None = None,
    ):
        self.x, self.y, self.z = _components(value, y, z)
        return self

    def array(self) -> list[float]:
        return [self.x, self.y, self.z]

    def tuple(self) -> tuple[float, float, float]:
        return self.x, self.y, self.z

    def to_string(self) -> str:
        return f"[{self.x:g}, {self.y:g}, {self.z:g}]"

    def get_value(self, index: int | str) -> float:
        if isinstance(index, str):
            match index:
                case "x":
                    return self.x
                case "y":
                    return self.y
                case "z":
                    return self.z
                case _:
                    raise IndexError("Vector component name must be 'x', 'y', or 'z'.")
        return self[index]

    def set_value(self, index: int | str, value: Number):
        if isinstance(index, str):
            match index:
                case "x":
                    self.x = float(value)
                case "y":
                    self.y = float(value)
                case "z":
                    self.z = float(value)
                case _:
                    raise IndexError("Vector component name must be 'x', 'y', or 'z'.")
            return self
        self[index] = value
        return self

    def mag(self) -> float:
        return math.sqrt(self.mag_sq())

    def mag_sq(self) -> float:
        return self.x * self.x + self.y * self.y + self.z * self.z

    def normalize(self):
        magnitude = self.mag()
        if magnitude != 0:
            cast(Any, self).div(magnitude)
        return self

    def set_mag(self, length: Number):
        return cast(Any, self.normalize()).mult(length)

    def limit(self, maximum: Number):
        max_value = float(maximum)
        if self.mag_sq() > max_value * max_value:
            self.set_mag(max_value)
        return self

    def clamp_to_zero(self, *, abs_tol: float = 1e-12):
        if abs(self.x) <= abs_tol:
            self.x = 0.0
        if abs(self.y) <= abs_tol:
            self.y = 0.0
        if abs(self.z) <= abs_tol:
            self.z = 0.0
        return self

    def __rsub__(self, other: object | Iterable[Number] | Number):
        if isinstance(other, int | float):
            vector_type = cast("type[Any]", type(self))
            return cast(Any, vector_type(other, other, other)).sub(self)
        vector_type = cast("type[Any]", type(self))
        return cast(Any, vector_type(other)).sub(self)

    def __round__(self, ndigits: int | None = None):
        if ndigits is None:
            vector_type = cast("type[Any]", type(self))
            return vector_type(round(self.x), round(self.y), round(self.z))
        vector_type = cast("type[Any]", type(self))
        return vector_type(
            round(self.x, ndigits),
            round(self.y, ndigits),
            round(self.z, ndigits),
        )

    def rem(self, other: object | Iterable[Number] | Number):
        ox, oy, oz = _components(other)
        self.x %= ox
        self.y %= oy
        self.z %= oz
        return self

    def normalized(self):
        return self.copy().normalize()
