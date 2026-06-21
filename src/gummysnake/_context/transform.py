"""Transform, stack, and angle-mode methods for SketchContext."""

from __future__ import annotations

import math
from typing import Any

from gummysnake import constants as c
from gummysnake.core import math as gs_math
from gummysnake.core.state import StateStackEntry
from gummysnake.core.transform import Matrix2D
from gummysnake.exceptions import ArgumentValidationError


class TransformContextMixin:
    renderer: Any
    state: Any
    _material3d: Any
    _normal_material3d: bool
    _material3d_style_stack: list[tuple[Any, bool]]

    def _set_transform_matrix(self, matrix: Matrix2D) -> None:
        self.state.transform.set_matrix(matrix)

    def push(self) -> None:
        self.state.stack.append(
            StateStackEntry(
                self.state.style.copy(),
                self.state.transform.matrix,
                self.renderer.clip_depth(),
            )
        )
        self._material3d_style_stack.append((self._material3d, self._normal_material3d))

    def pop(self) -> None:
        if not self.state.stack:
            raise ArgumentValidationError("pop() called without matching push().")
        entry = self.state.stack.pop()
        self.state.style = entry.style
        self.state.transform.set_matrix(entry.matrix)
        self.renderer.restore_clip_depth(entry.clip_depth)
        self._material3d, self._normal_material3d = self._material3d_style_stack.pop()

    def translate(self, x: float, y: float) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.translation(float(x), float(y)))
        )

    def rotate(self, angle: float) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.rotation(self._angle(angle)))
        )

    def scale(self, x: float, y: float | None = None) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(
                Matrix2D.scaling(float(x), None if y is None else float(y))
            )
        )

    def shear_x(self, angle: float) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.shear_x(self._angle(angle)))
        )

    def shear_y(self, angle: float) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.shear_y(self._angle(angle)))
        )

    def apply_matrix(self, a: float, b: float, cc: float, d: float, e: float, f: float) -> None:
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D(a, b, cc, d, e, f))
        )

    def reset_matrix(self) -> None:
        self._set_transform_matrix(Matrix2D.identity())

    def angle_mode(self, mode: c.AngleMode) -> None:
        if mode not in {c.RADIANS, c.DEGREES}:
            raise ArgumentValidationError(f"Unsupported angle mode {mode!r}.")
        self.angle_mode_value = mode
        gs_math.set_angle_mode(mode)

    def _angle(self, value: float) -> float:
        mode = getattr(self, "angle_mode_value", c.RADIANS)
        return math.radians(value) if mode == c.DEGREES else float(value)
