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

    def _set_transform_matrix(self, matrix: Matrix2D, *, sync_renderer: bool = True) -> None:
        self.state.transform.set_matrix(matrix)
        if sync_renderer:
            sync_matrix = getattr(self.renderer, "set_current_matrix", None)
            if callable(sync_matrix):
                sync_matrix(matrix)
        else:
            remember = getattr(self.renderer, "remember_current_matrix", None)
            if callable(remember):
                remember(matrix)

    def push(self) -> None:
        push_state = getattr(self.renderer, "push_canvas_state", None)
        if callable(push_state):
            push_state()
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
        pop_state = getattr(self.renderer, "pop_canvas_state", None)
        if callable(pop_state):
            pop_state()
        self.state.style = entry.style
        self.state.transform.matrix = entry.matrix
        self.state.transform.revision += 1
        self.renderer.restore_clip_depth(entry.clip_depth)
        self._material3d, self._normal_material3d = self._material3d_style_stack.pop()

    def translate(self, x: float, y: float) -> None:
        translate = getattr(self.renderer, "translate", None)
        if callable(translate):
            translate(float(x), float(y))
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.translation(float(x), float(y))),
            sync_renderer=False,
        )

    def rotate(self, angle: float) -> None:
        radians = self._angle(angle)
        rotate = getattr(self.renderer, "rotate", None)
        if callable(rotate):
            rotate(radians)
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.rotation(radians)),
            sync_renderer=False,
        )

    def scale(self, x: float, y: float | None = None) -> None:
        scale = getattr(self.renderer, "scale", None)
        if callable(scale):
            scale(float(x), None if y is None else float(y))
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(
                Matrix2D.scaling(float(x), None if y is None else float(y))
            ),
            sync_renderer=False,
        )

    def shear_x(self, angle: float) -> None:
        radians = self._angle(angle)
        shear_x = getattr(self.renderer, "shear_x", None)
        if callable(shear_x):
            shear_x(radians)
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.shear_x(radians)),
            sync_renderer=False,
        )

    def shear_y(self, angle: float) -> None:
        radians = self._angle(angle)
        shear_y = getattr(self.renderer, "shear_y", None)
        if callable(shear_y):
            shear_y(radians)
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(Matrix2D.shear_y(radians)),
            sync_renderer=False,
        )

    def apply_matrix(self, a: float, b: float, cc: float, d: float, e: float, f: float) -> None:
        matrix = Matrix2D(a, b, cc, d, e, f)
        apply_matrix = getattr(self.renderer, "apply_matrix", None)
        if callable(apply_matrix):
            apply_matrix(matrix)
        self._set_transform_matrix(
            self.state.transform.matrix.multiply(matrix),
            sync_renderer=False,
        )

    def reset_matrix(self) -> None:
        reset_matrix = getattr(self.renderer, "reset_matrix", None)
        if callable(reset_matrix):
            reset_matrix()
        self._set_transform_matrix(Matrix2D.identity(), sync_renderer=False)

    def angle_mode(self, mode: c.AngleMode) -> None:
        if mode not in {c.RADIANS, c.DEGREES}:
            raise ArgumentValidationError(f"Unsupported angle mode {mode!r}.")
        self.angle_mode_value = mode
        gs_math.set_angle_mode(mode)

    def _angle(self, value: float) -> float:
        mode = getattr(self, "angle_mode_value", c.RADIANS)
        return math.radians(value) if mode == c.DEGREES else float(value)
