"""Basic vector protocol and mutation helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from typing import Any, Self, cast

from gummysnake.core.vector.common import Number, _components, _VectorBasicOps


class VectorBasicMixin:
    """Public VectorBasicMixin value."""
    x: float
    y: float
    z: float

    def __repr__(self) -> str:
        """Return a debugging representation of this object.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str`.
        """
        return f"Vector({self.x:g}, {self.y:g}, {self.z:g})"

    def __str__(self) -> str:
        return self.to_string()

    def __iter__(self) -> Iterator[float]:
        """Iterate over this object.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Iterator[float]`.
        """
        yield self.x
        yield self.y
        yield self.z

    def __len__(self) -> int:
        """Return the number of values in this object.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return 3

    def __getitem__(self, index: int) -> float:
        """Return a value by index.
        
        Args:
            index: The index value. Expected type: `int`.
        
        Returns:
            The return value. Type: `float`.
        """
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
        """Set a value by index.
        
        Args:
            index: The index value. Expected type: `int`.
            value: The value value. Expected type: `Number`.
        
        Returns:
            None.
        """
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
        """Return whether this object equals another value.
        
        Args:
            other: The other value. Expected type: `object`.
        
        Returns:
            The return value. Type: `bool`.
        """
        if not isinstance(other, type(self)):
            return NotImplemented
        return self.equals(other)

    def equals(self, other: object | Iterable[Number], *, abs_tol: float = 1e-09) -> bool:
        """Equals for this VectorBasicMixin.
        
        Args:
            other: The other value. Expected type: `object | Iterable[Number]`.
            abs_tol: The abs tol value. Expected type: `float`. Defaults to `1e-09`.
        
        Returns:
            The return value. Type: `bool`.
        """
        ox, oy, oz = _components(other)
        return (
            math.isclose(self.x, ox, abs_tol=abs_tol)
            and math.isclose(self.y, oy, abs_tol=abs_tol)
            and math.isclose(self.z, oz, abs_tol=abs_tol)
        )

    def copy(self) -> Self:
        """Copy for this VectorBasicMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Self`.
        """
        vector_type = cast("type[Any]", type(self))
        return vector_type(self.x, self.y, self.z)

    def set(
        self,
        value: object | Iterable[Number] | Number,
        y: Number | None = None,
        z: Number | None = None,
    ) -> Self:
        """Set for this VectorBasicMixin.
        
        Args:
            value: The value value. Expected type: `object | Iterable[Number] | Number`.
            y: The y value. Expected type: `Number | None`. Defaults to `None`.
            z: The z value. Expected type: `Number | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Self`.
        """
        self.x, self.y, self.z = _components(value, y, z)
        return self

    def array(self) -> list[float]:
        """Array for this VectorBasicMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `list[float]`.
        """
        return [self.x, self.y, self.z]

    def tuple(self) -> tuple[float, float, float]:
        """Tuple for this VectorBasicMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[float, float, float]`.
        """
        return self.x, self.y, self.z

    def to_string(self) -> str:
        """To string for this VectorBasicMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str`.
        """
        return f"[{self.x:g}, {self.y:g}, {self.z:g}]"

    def get_value(self, index: int | str) -> float:
        """Return the current value value.
        
        Args:
            index: The index value. Expected type: `int | str`.
        
        Returns:
            The return value. Type: `float`.
        """
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

    def set_value(self, index: int | str, value: Number) -> Self:
        """Set the value value.
        
        Args:
            index: The index value. Expected type: `int | str`.
            value: The value value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Self`.
        """
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
        """Mag for this VectorBasicMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return math.sqrt(self.mag_sq())

    def mag_sq(self) -> float:
        """Mag sq for this VectorBasicMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self.x * self.x + self.y * self.y + self.z * self.z

    def normalize(self) -> Self:
        """Normalize for this VectorBasicMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Self`.
        """
        magnitude = self.mag()
        if magnitude != 0:
            cast(_VectorBasicOps, self).div(magnitude)
        return self

    def set_mag(self, length: Number) -> Self:
        """Set the mag value.
        
        Args:
            length: The length value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Self`.
        """
        return cast(Self, cast(_VectorBasicOps, self.normalize()).mult(length))

    def limit(self, maximum: Number) -> Self:
        """Limit for this VectorBasicMixin.
        
        Args:
            maximum: The maximum value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Self`.
        """
        max_value = float(maximum)
        if self.mag_sq() > max_value * max_value:
            self.set_mag(max_value)
        return self

    def clamp_to_zero(self, *, abs_tol: float = 1e-12) -> Self:
        """Clamp to zero for this VectorBasicMixin.
        
        Args:
            abs_tol: The abs tol value. Expected type: `float`. Defaults to `1e-12`.
        
        Returns:
            The return value. Type: `Self`.
        """
        if abs(self.x) <= abs_tol:
            self.x = 0.0
        if abs(self.y) <= abs_tol:
            self.y = 0.0
        if abs(self.z) <= abs_tol:
            self.z = 0.0
        return self

    def __rsub__(self, other: object | Iterable[Number] | Number) -> Self:
        if isinstance(other, int | float):
            vector_type = cast("type[Any]", type(self))
            return cast(Self, vector_type(other, other, other).sub(self))
        vector_type = cast("type[Any]", type(self))
        return cast(Self, vector_type(other).sub(self))

    def __round__(self, ndigits: int | None = None) -> Self:
        if ndigits is None:
            vector_type = cast("type[Any]", type(self))
            return vector_type(round(self.x), round(self.y), round(self.z))
        vector_type = cast("type[Any]", type(self))
        return vector_type(
            round(self.x, ndigits),
            round(self.y, ndigits),
            round(self.z, ndigits),
        )

    def rem(self, other: object | Iterable[Number] | Number) -> Self:
        """Rem for this VectorBasicMixin.
        
        Args:
            other: The other value. Expected type: `object | Iterable[Number] | Number`.
        
        Returns:
            The return value. Type: `Self`.
        """
        ox, oy, oz = _components(other)
        self.x %= ox
        self.y %= oy
        self.z %= oz
        return self

    def normalized(self) -> Self:
        """Normalized for this VectorBasicMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Self`.
        """
        return self.copy().normalize()
