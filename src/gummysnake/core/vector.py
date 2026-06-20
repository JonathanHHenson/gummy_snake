"""Gummy Snake Vector-like mutable vector class."""

from __future__ import annotations

import math
import random as _random
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, cast

from gummysnake import constants as c
from gummysnake.core import math as gs_math

Number = int | float


class _DualMethod:
    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def __get__(self, obj: object | None, owner: type) -> Callable[..., Any]:
        def bound(*args: Any, **kwargs: Any) -> Any:
            return self.func(obj, *args, **kwargs)

        return bound


def _components(
    value: Vector | Iterable[Number] | Number,
    y: Number | None = None,
    z: Number | None = None,
) -> tuple[float, float, float]:
    if isinstance(value, Vector):
        return value.x, value.y, value.z
    if y is not None or z is not None:
        scalar = cast(Number, value)
        return float(scalar), float(0 if y is None else y), float(0 if z is None else z)
    if isinstance(value, int | float):
        return float(value), float(value), float(value)
    items = tuple(value)
    if len(items) == 2:
        return float(items[0]), float(items[1]), 0.0
    if len(items) == 3:
        return float(items[0]), float(items[1]), float(items[2])
    msg = "Vector operands must be a scalar, Vector, or 2/3-item iterable."
    raise TypeError(msg)


@dataclass(slots=True)
class Vector:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __init__(self, x: Number | Iterable[Number] = 0, y: Number = 0, z: Number = 0) -> None:
        if not isinstance(x, int | float) and y == 0 and z == 0:
            self.x, self.y, self.z = _components(x)
        else:
            scalar_x = cast(Number, x)
            self.x = float(scalar_x)
            self.y = float(y)
            self.z = float(z)

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
        if not isinstance(other, Vector):
            return NotImplemented
        return self.equals(other)

    def equals(self, other: Vector | Iterable[Number], *, abs_tol: float = 1e-09) -> bool:
        ox, oy, oz = _components(other)
        return (
            math.isclose(self.x, ox, abs_tol=abs_tol)
            and math.isclose(self.y, oy, abs_tol=abs_tol)
            and math.isclose(self.z, oz, abs_tol=abs_tol)
        )

    def copy(self) -> Vector:
        return Vector(self.x, self.y, self.z)

    def set(
        self,
        value: Vector | Iterable[Number] | Number,
        y: Number | None = None,
        z: Number | None = None,
    ) -> Vector:
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

    def set_value(self, index: int | str, value: Number) -> Vector:
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

    @_DualMethod
    def add(
        self: Vector | None,
        value: Vector | Iterable[Number] | Number,
        other: Vector | Iterable[Number] | Number | None = None,
        z: Number | None = None,
    ) -> Vector:
        target = Vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError("Vector.add() requires two vectors when called as a class helper.")
        operand = cast(Vector | Iterable[Number] | Number, other if self is None else value)
        dx, dy, dz = _components(operand, None, z)
        target.x += dx
        target.y += dy
        target.z += dz
        return target

    @_DualMethod
    def sub(
        self: Vector | None,
        value: Vector | Iterable[Number] | Number,
        other: Vector | Iterable[Number] | Number | None = None,
        z: Number | None = None,
    ) -> Vector:
        target = Vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError("Vector.sub() requires two vectors when called as a class helper.")
        operand = cast(Vector | Iterable[Number] | Number, other if self is None else value)
        dx, dy, dz = _components(operand, None, z)
        target.x -= dx
        target.y -= dy
        target.z -= dz
        return target

    @_DualMethod
    def mult(
        self: Vector | None,
        vector_or_value: Vector | Iterable[Number] | Number,
        value: Number | None = None,
    ) -> Vector:
        target = Vector(vector_or_value) if self is None else self
        factor = vector_or_value if self is not None else value
        if factor is None:
            msg = "Vector.mult() requires a scalar multiplier."
            raise TypeError(msg)
        scalar = cast(Number, factor)
        target.x *= float(scalar)
        target.y *= float(scalar)
        target.z *= float(scalar)
        return target

    @_DualMethod
    def div(
        self: Vector | None,
        vector_or_value: Vector | Iterable[Number] | Number,
        value: Number | None = None,
    ) -> Vector:
        target = Vector(vector_or_value) if self is None else self
        divisor = vector_or_value if self is not None else value
        if divisor is None:
            msg = "Vector.div() requires a scalar divisor."
            raise TypeError(msg)
        divisor = float(cast(Number, divisor))
        if divisor == 0:
            msg = "Vector.div() cannot divide by zero."
            raise ZeroDivisionError(msg)
        target.x /= divisor
        target.y /= divisor
        target.z /= divisor
        return target

    def mag(self) -> float:
        return math.sqrt(self.mag_sq())

    def mag_sq(self) -> float:
        return self.x * self.x + self.y * self.y + self.z * self.z

    def normalize(self) -> Vector:
        magnitude = self.mag()
        if magnitude != 0:
            self.div(magnitude)
        return self

    def set_mag(self, length: Number) -> Vector:
        return self.normalize().mult(length)

    def limit(self, maximum: Number) -> Vector:
        max_value = float(maximum)
        if self.mag_sq() > max_value * max_value:
            self.set_mag(max_value)
        return self

    def clamp_to_zero(self, *, abs_tol: float = 1e-12) -> Vector:
        if abs(self.x) <= abs_tol:
            self.x = 0.0
        if abs(self.y) <= abs_tol:
            self.y = 0.0
        if abs(self.z) <= abs_tol:
            self.z = 0.0
        return self

    def heading(self) -> float:
        return gs_math.atan2(self.y, self.x)

    def set_heading(self, angle: Number) -> Vector:
        magnitude = self.mag()
        radians = gs_math.radians(angle) if gs_math.get_angle_mode() == c.DEGREES else float(angle)
        self.x = math.cos(radians) * magnitude
        self.y = math.sin(radians) * magnitude
        return self

    def rotate(self, angle: Number) -> Vector:
        radians = gs_math.radians(angle) if gs_math.get_angle_mode() == c.DEGREES else float(angle)
        cosine = math.cos(radians)
        sine = math.sin(radians)
        x = self.x * cosine - self.y * sine
        y = self.x * sine + self.y * cosine
        self.x = x
        self.y = y
        return self

    @_DualMethod
    def dot(
        self: Vector | None,
        value: Vector | Iterable[Number] | Number,
        other: Vector | Iterable[Number] | Number | None = None,
        z: Number | None = None,
    ) -> float:
        target = Vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError("Vector.dot() requires two vectors when called as a class helper.")
        operand = cast(Vector | Iterable[Number] | Number, other if self is None else value)
        dx, dy, dz = _components(operand, None, z)
        return target.x * dx + target.y * dy + target.z * dz

    @_DualMethod
    def angle_between(
        self: Vector | None,
        value: Vector | Iterable[Number],
        other: Vector | Iterable[Number] | None = None,
    ) -> float:
        target = Vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError(
                "Vector.angle_between() requires two vectors when called as a class helper."
            )
        operand = cast(Vector | Iterable[Number], other if self is None else value)
        ox, oy, oz = _components(operand)
        mag_product = target.mag() * math.sqrt(ox * ox + oy * oy + oz * oz)
        if mag_product == 0:
            return 0.0
        dot = max(-1.0, min(1.0, (target.x * ox + target.y * oy + target.z * oz) / mag_product))
        radians = math.acos(dot)
        return gs_math.degrees(radians) if gs_math.get_angle_mode() == c.DEGREES else radians

    @_DualMethod
    def cross(
        self: Vector | None,
        value: Vector | Iterable[Number],
        other: Vector | Iterable[Number] | None = None,
    ) -> Vector:
        target = Vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError("Vector.cross() requires two vectors when called as a class helper.")
        operand = cast(Vector | Iterable[Number], other if self is None else value)
        dx, dy, dz = _components(operand)
        return Vector(
            target.y * dz - target.z * dy,
            target.z * dx - target.x * dz,
            target.x * dy - target.y * dx,
        )

    @_DualMethod
    def dist(
        self: Vector | None,
        value: Vector | Iterable[Number],
        other: Vector | Iterable[Number] | None = None,
    ) -> float:
        target = Vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError("Vector.dist() requires two vectors when called as a class helper.")
        operand = cast(Vector | Iterable[Number], other if self is None else value)
        dx, dy, dz = _components(operand)
        return math.sqrt((target.x - dx) ** 2 + (target.y - dy) ** 2 + (target.z - dz) ** 2)

    @_DualMethod
    def lerp(
        self: Vector | None,
        value: Vector | Iterable[Number],
        other: Vector | Iterable[Number] | Number,
        amount: Number | None = None,
    ) -> Vector:
        target = Vector(value) if self is None else self
        if self is None and amount is None:
            raise TypeError("Vector.lerp() requires an amount when called as a class helper.")
        operand = cast(Vector | Iterable[Number], other if self is None else value)
        t = cast(Number, amount if self is None else other)
        dx, dy, dz = _components(operand)
        target.x = gs_math.lerp(target.x, dx, t)
        target.y = gs_math.lerp(target.y, dy, t)
        target.z = gs_math.lerp(target.z, dz, t)
        return target

    @_DualMethod
    def slerp(
        self: Vector | None,
        value: Vector | Iterable[Number],
        other: Vector | Iterable[Number] | Number,
        amount: Number | None = None,
    ) -> Vector:
        target = Vector(value) if self is None else self
        if self is None and amount is None:
            raise TypeError("Vector.slerp() requires an amount when called as a class helper.")
        operand = Vector(cast(Vector | Iterable[Number], other if self is None else value))
        t = float(cast(Number, amount if self is None else other))
        start_mag = target.mag()
        end_mag = operand.mag()
        if start_mag == 0 or end_mag == 0:
            return target.lerp(operand, t)
        start = target.copy().div(start_mag)
        end = operand.copy().div(end_mag)
        dot = max(-1.0, min(1.0, start.dot(end)))
        theta = math.acos(dot) * t
        relative = end.sub(start.copy().mult(dot)).normalize()
        direction = start.mult(math.cos(theta)).add(relative.mult(math.sin(theta)))
        return target.set(direction.mult(gs_math.lerp(start_mag, end_mag, t)))

    def reflect(self, normal: Vector | Iterable[Number]) -> Vector:
        n = Vector(normal).normalize()
        return self.sub(n.mult(2 * self.dot(n)))

    def __add__(self, other: Vector | Iterable[Number] | Number) -> Vector:
        return self.copy().add(other)

    def __sub__(self, other: Vector | Iterable[Number] | Number) -> Vector:
        return self.copy().sub(other)

    def __mul__(self, other: Number) -> Vector:
        return self.copy().mult(other)

    def __rmul__(self, other: Number) -> Vector:
        return self.__mul__(other)

    def __truediv__(self, other: Number) -> Vector:
        return self.copy().div(other)

    def __mod__(self, other: Vector | Iterable[Number] | Number) -> Vector:
        ox, oy, oz = _components(other)
        return Vector(self.x % ox, self.y % oy, self.z % oz)

    def rem(self, other: Vector | Iterable[Number] | Number) -> Vector:
        self.x, self.y, self.z = (self % other).tuple()
        return self

    def __neg__(self) -> Vector:
        return Vector(-self.x, -self.y, -self.z)

    def __abs__(self) -> float:
        return self.mag()

    def __matmul__(self, other: Vector | Iterable[Number] | Number) -> float:
        return self.dot(other)

    def __round__(self, ndigits: int | None = None) -> Vector:
        if ndigits is None:
            return Vector(round(self.x), round(self.y), round(self.z))
        return Vector(
            round(self.x, ndigits),
            round(self.y, ndigits),
            round(self.z, ndigits),
        )

    def __radd__(self, other: Vector | Iterable[Number] | Number) -> Vector:
        return self.__add__(other)

    def __rsub__(self, other: Vector | Iterable[Number] | Number) -> Vector:
        if isinstance(other, int | float):
            return Vector(other, other, other).sub(self)
        return Vector(other).sub(self)

    def normalized(self) -> Vector:
        return self.copy().normalize()

    @staticmethod
    def from_angle(angle: Number, length: Number = 1) -> Vector:
        radians = gs_math.radians(angle) if gs_math.get_angle_mode() == c.DEGREES else float(angle)
        return Vector(math.cos(radians) * float(length), math.sin(radians) * float(length), 0)

    @staticmethod
    def from_angles(theta: Number, phi: Number, length: Number = 1) -> Vector:
        theta_radians = (
            gs_math.radians(theta) if gs_math.get_angle_mode() == c.DEGREES else float(theta)
        )
        phi_radians = gs_math.radians(phi) if gs_math.get_angle_mode() == c.DEGREES else float(phi)
        radius = float(length)
        sin_phi = math.sin(phi_radians)
        return Vector(
            radius * sin_phi * math.cos(theta_radians),
            radius * sin_phi * math.sin(theta_radians),
            radius * math.cos(phi_radians),
        )

    @staticmethod
    def random_2d() -> Vector:
        return Vector.from_angle(_random.random() * math.tau)

    @staticmethod
    def random_3d() -> Vector:
        z = _random.uniform(-1.0, 1.0)
        theta = _random.random() * math.tau
        radius = math.sqrt(1 - z * z)
        return Vector(radius * math.cos(theta), radius * math.sin(theta), z)

    random2d = random_2d
    random3d = random_3d


def create_vector(x: Number = 0, y: Number = 0, z: Number = 0) -> Vector:
    return Vector(x, y, z)


__all__ = ["Vector", "create_vector"]
