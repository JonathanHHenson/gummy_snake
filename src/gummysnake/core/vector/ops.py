"""Vector arithmetic, geometry, and constructors."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any, Self, cast

from gummysnake import constants as c
from gummysnake.core import math as gs_math
from gummysnake.core.random import shared_rng
from gummysnake.core.vector.common import (
    Number,
    _components,
    _DualMethod,
    _VectorFullOps,
    make_vector,
)


class VectorOpsMixin:
    """Public VectorOpsMixin value."""

    x: float
    y: float
    z: float

    @_DualMethod
    def add(
        self,
        value: object | Iterable[Number] | Number,
        other: object | Iterable[Number] | Number | None = None,
        z: Number | None = None,
    ) -> Self:
        target = make_vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError("Vector.add() requires two vectors when called as a class helper.")
        operand = other if self is None else value
        dx, dy, dz = _components(operand, None, z)
        target.x += dx
        target.y += dy
        target.z += dz
        return cast(Self, target)

    @_DualMethod
    def sub(
        self,
        value: object | Iterable[Number] | Number,
        other: object | Iterable[Number] | Number | None = None,
        z: Number | None = None,
    ) -> Self:
        target = make_vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError("Vector.sub() requires two vectors when called as a class helper.")
        operand = other if self is None else value
        dx, dy, dz = _components(operand, None, z)
        target.x -= dx
        target.y -= dy
        target.z -= dz
        return cast(Self, target)

    @_DualMethod
    def mult(
        self, vector_or_value: object | Iterable[Number] | Number, value: Number | None = None
    ) -> Self:
        target = make_vector(vector_or_value) if self is None else self
        factor = vector_or_value if self is not None else value
        if factor is None:
            raise TypeError("Vector.mult() requires a scalar multiplier.")
        target.x *= float(cast(Number, factor))
        target.y *= float(cast(Number, factor))
        target.z *= float(cast(Number, factor))
        return cast(Self, target)

    @_DualMethod
    def div(
        self, vector_or_value: object | Iterable[Number] | Number, value: Number | None = None
    ) -> Self:
        target = make_vector(vector_or_value) if self is None else self
        divisor = vector_or_value if self is not None else value
        if divisor is None:
            raise TypeError("Vector.div() requires a scalar divisor.")
        divisor = float(cast(Number, divisor))
        if divisor == 0:
            raise ZeroDivisionError("Vector.div() cannot divide by zero.")
        target.x /= divisor
        target.y /= divisor
        target.z /= divisor
        return cast(Self, target)

    def heading(self) -> float:
        return gs_math.atan2(self.y, self.x)

    def set_heading(self, angle: Number) -> Self:
        magnitude = cast(_VectorFullOps, self).mag()
        radians = gs_math.radians(angle) if gs_math.get_angle_mode() == c.DEGREES else float(angle)
        self.x = math.cos(radians) * magnitude
        self.y = math.sin(radians) * magnitude
        return self

    def rotate(self, angle: Number) -> Self:
        radians = gs_math.radians(angle) if gs_math.get_angle_mode() == c.DEGREES else float(angle)
        cosine = math.cos(radians)
        sine = math.sin(radians)
        self.x, self.y = self.x * cosine - self.y * sine, self.x * sine + self.y * cosine
        return self

    @_DualMethod
    def dot(
        self,
        value: object | Iterable[Number] | Number,
        other: object | Iterable[Number] | Number | None = None,
        z: Number | None = None,
    ) -> float:
        target = make_vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError("Vector.dot() requires two vectors when called as a class helper.")
        dx, dy, dz = _components(other if self is None else value, None, z)
        return target.x * dx + target.y * dy + target.z * dz

    @_DualMethod
    def angle_between(
        self, value: object | Iterable[Number], other: object | Iterable[Number] | None = None
    ) -> float:
        target = make_vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError(
                "Vector.angle_between() requires two vectors when called as a class helper."
            )
        ox, oy, oz = _components(other if self is None else value)
        mag_product = cast(_VectorFullOps, target).mag() * math.sqrt(ox * ox + oy * oy + oz * oz)
        if mag_product == 0:
            return 0.0
        dot = max(-1.0, min(1.0, (target.x * ox + target.y * oy + target.z * oz) / mag_product))
        radians = math.acos(dot)
        return gs_math.degrees(radians) if gs_math.get_angle_mode() == c.DEGREES else radians

    @_DualMethod
    def cross(
        self, value: object | Iterable[Number], other: object | Iterable[Number] | None = None
    ) -> Self:
        target = make_vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError("Vector.cross() requires two vectors when called as a class helper.")
        dx, dy, dz = _components(other if self is None else value)
        vector_type = cast("type[Any]", type(target))
        return vector_type(
            target.y * dz - target.z * dy,
            target.z * dx - target.x * dz,
            target.x * dy - target.y * dx,
        )

    @_DualMethod
    def dist(
        self, value: object | Iterable[Number], other: object | Iterable[Number] | None = None
    ) -> float:
        target = make_vector(value) if self is None else self
        if self is None and other is None:
            raise TypeError("Vector.dist() requires two vectors when called as a class helper.")
        dx, dy, dz = _components(other if self is None else value)
        return math.sqrt((target.x - dx) ** 2 + (target.y - dy) ** 2 + (target.z - dz) ** 2)

    @_DualMethod
    def lerp(
        self,
        value: object | Iterable[Number],
        other: object | Iterable[Number] | Number,
        amount: Number | None = None,
    ) -> Self:
        target = make_vector(value) if self is None else self
        if self is None and amount is None:
            raise TypeError("Vector.lerp() requires an amount when called as a class helper.")
        operand = other if self is None else value
        t = cast(Number, amount if self is None else other)
        dx, dy, dz = _components(operand)
        target.x = gs_math.lerp(target.x, dx, t)
        target.y = gs_math.lerp(target.y, dy, t)
        target.z = gs_math.lerp(target.z, dz, t)
        return cast(Self, target)

    @_DualMethod
    def slerp(
        self,
        value: object | Iterable[Number],
        other: object | Iterable[Number] | Number,
        amount: Number | None = None,
    ) -> Self:
        target = make_vector(value) if self is None else self
        if self is None and amount is None:
            raise TypeError("Vector.slerp() requires an amount when called as a class helper.")
        operand = make_vector(other if self is None else value)
        t = float(cast(Number, amount if self is None else other))
        target_ops = cast(_VectorFullOps, target)
        operand_ops = cast(_VectorFullOps, operand)
        start_mag = target_ops.mag()
        end_mag = operand_ops.mag()
        if start_mag == 0 or end_mag == 0:
            return cast(Self, target_ops.lerp(operand, t))
        start = target_ops.copy().div(start_mag)
        end = operand_ops.copy().div(end_mag)
        dot = max(-1.0, min(1.0, start.dot(end)))
        theta = math.acos(dot) * t
        relative = end.sub(start.copy().mult(dot)).normalize()
        direction = start.mult(math.cos(theta)).add(relative.mult(math.sin(theta)))
        return cast(Self, target_ops.set(direction.mult(gs_math.lerp(start_mag, end_mag, t))))

    def reflect(self, normal: object | Iterable[Number]) -> Self:
        vector_type = cast("type[Any]", type(self))
        n = vector_type(normal).normalize()
        return self.sub(n.mult(2 * self.dot(n)))

    def __add__(self, other: object | Iterable[Number] | Number) -> Self:
        return cast(Self, cast(_VectorFullOps, self).copy().add(other))

    def __sub__(self, other: object | Iterable[Number] | Number) -> Self:
        return cast(Self, cast(_VectorFullOps, self).copy().sub(other))

    def __mul__(self, other: Number) -> Self:
        return cast(Self, cast(_VectorFullOps, self).copy().mult(other))

    def __rmul__(self, other: Number) -> Self:
        return self.__mul__(other)

    def __truediv__(self, other: Number) -> Self:
        return cast(Self, cast(_VectorFullOps, self).copy().div(other))

    def __mod__(self, other: object | Iterable[Number] | Number) -> Self:
        ox, oy, oz = _components(other)
        vector_type = cast("type[Any]", type(self))
        return vector_type(self.x % ox, self.y % oy, self.z % oz)

    def __neg__(self) -> Self:
        vector_type = cast("type[Any]", type(self))
        return vector_type(-self.x, -self.y, -self.z)

    def __abs__(self) -> float:
        return cast(_VectorFullOps, self).mag()

    def __matmul__(self, other: object | Iterable[Number] | Number) -> float:
        return self.dot(other)

    def __radd__(self, other: object | Iterable[Number] | Number) -> Self:
        return self.__add__(other)

    @staticmethod
    def from_angle(angle: Number, length: Number = 1) -> Any:
        radians = gs_math.radians(angle) if gs_math.get_angle_mode() == c.DEGREES else float(angle)
        return make_vector(math.cos(radians) * float(length), math.sin(radians) * float(length), 0)

    @staticmethod
    def from_angles(theta: Number, phi: Number, length: Number = 1) -> Any:
        theta_radians = (
            gs_math.radians(theta) if gs_math.get_angle_mode() == c.DEGREES else float(theta)
        )
        phi_radians = gs_math.radians(phi) if gs_math.get_angle_mode() == c.DEGREES else float(phi)
        radius = float(length)
        sin_phi = math.sin(phi_radians)
        return make_vector(
            radius * sin_phi * math.cos(theta_radians),
            radius * sin_phi * math.sin(theta_radians),
            radius * math.cos(phi_radians),
        )

    @staticmethod
    def random_2d() -> Any:
        angle = shared_rng().random() * math.tau
        return make_vector(math.cos(angle), math.sin(angle), 0)

    @staticmethod
    def random_3d() -> Any:
        z = shared_rng().uniform(-1.0, 1.0)
        theta = shared_rng().random() * math.tau
        radius = math.sqrt(1 - z * z)
        return make_vector(radius * math.cos(theta), radius * math.sin(theta), z)
