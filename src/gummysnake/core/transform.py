"""2D affine transform utilities."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Matrix2D:
    """Canvas-style affine matrix: x' = ax + cy + e, y' = bx + dy + f."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def multiply(self, other: Matrix2D) -> Matrix2D:
        return Matrix2D(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )

    def transform_point(self, x: float, y: float) -> tuple[float, float]:
        return self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f

    def inverse(self) -> Matrix2D:
        determinant = self.a * self.d - self.b * self.c
        if abs(determinant) < 1e-12:
            raise ValueError("Matrix is not invertible.")
        return Matrix2D(
            self.d / determinant,
            -self.b / determinant,
            -self.c / determinant,
            self.a / determinant,
            (self.c * self.f - self.d * self.e) / determinant,
            (self.b * self.e - self.a * self.f) / determinant,
        )

    @classmethod
    def identity(cls) -> Matrix2D:
        return cls()

    @classmethod
    def translation(cls, x: float, y: float) -> Matrix2D:
        return cls(1.0, 0.0, 0.0, 1.0, x, y)

    @classmethod
    def rotation(cls, angle: float) -> Matrix2D:
        cosine = math.cos(angle)
        sine = math.sin(angle)
        return cls(cosine, sine, -sine, cosine, 0.0, 0.0)

    @classmethod
    def scaling(cls, x: float, y: float | None = None) -> Matrix2D:
        sy = x if y is None else y
        return cls(x, 0.0, 0.0, sy, 0.0, 0.0)

    @classmethod
    def shear_x(cls, angle: float) -> Matrix2D:
        return cls(1.0, 0.0, math.tan(angle), 1.0, 0.0, 0.0)

    @classmethod
    def shear_y(cls, angle: float) -> Matrix2D:
        return cls(1.0, math.tan(angle), 0.0, 1.0, 0.0, 0.0)
