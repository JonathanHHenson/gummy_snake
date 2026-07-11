"""Zero-allocation fast 3D transform state for :class:`FastDrawScope`."""

# mypy: disable-error-code=misc
# State is stored only in the public facade's frozen slot layout.
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gummysnake._fast_draw_math import (
    _mat4_axis_angle,
    _mat4_is_translation,
    _mat4_multiply,
    _mat4_post_rotate_x,
    _mat4_post_rotate_y,
    _mat4_post_rotate_z,
    _mat4_post_scale,
    _mat4_post_translate,
    _mat4_quaternion,
    _mat4_scale,
    _mat4_translation,
    _mat4_translation_then_rotation,
    _sequence3,
    _sequence4,
)
from gummysnake.drawing.software3d.payloads import (
    _IDENTITY4,
    Matrix4Payload,
    _coerce_matrix4_payload,
)

if TYPE_CHECKING:
    from gummysnake.context import SketchContext


class FastTransformStateMixin:
    """Maintain the frame-local 3D model transform without wrapper allocation."""

    __slots__ = ()

    _context: SketchContext
    _transform3d: Matrix4Payload
    _transform3d_active: bool
    _transform3d_stack: list[tuple[Matrix4Payload, bool]]

    def _compose_transform3d(self, transform: Matrix4Payload) -> None:
        self._transform3d = (
            _mat4_multiply(self._transform3d, transform) if self._transform3d_active else transform
        )
        self._transform3d_active = True

    def _model_transform3d_payload(self) -> Matrix4Payload | None:
        return self._transform3d if self._transform3d_active else None

    def push(self) -> None:
        """Push the fast 3D model transform stack."""
        self._transform3d_stack.append((self._transform3d, self._transform3d_active))

    def pop(self) -> None:
        """Restore the most recently pushed fast 3D model transform."""
        self._transform3d, self._transform3d_active = self._transform3d_stack.pop()

    def reset_matrix(self) -> None:
        """Reset the transform applied to subsequent fast 3D model draws."""
        self._transform3d = _IDENTITY4
        self._transform3d_active = False

    def translate(self, x: float, y: float, z: float = 0.0) -> None:
        """Translate subsequent fast 3D model draws by ``x``, ``y``, and ``z``."""
        fx = float(x)
        fy = float(y)
        fz = float(z)
        if self._transform3d_active:
            self._transform3d = _mat4_post_translate(self._transform3d, fx, fy, fz)
        else:
            self._transform3d = _mat4_translation(fx, fy, fz)
            self._transform3d_active = True

    def scale(self, x: float, y: float | None = None, z: float | None = None) -> None:
        """Scale subsequent fast 3D model draws, uniformly when only ``x`` is provided."""
        fx = float(x)
        if y is None and z is None:
            fy = fz = fx
        else:
            fy = fx if y is None else float(y)
            fz = 1.0 if z is None else float(z)
        if self._transform3d_active:
            self._transform3d = _mat4_post_scale(self._transform3d, fx, fy, fz)
        else:
            self._transform3d = _mat4_scale(fx, fy, fz)
            self._transform3d_active = True

    def apply_matrix_3d(self, matrix: Sequence[float] | Sequence[Sequence[float]]) -> None:
        """Compose a 4x4 matrix for subsequent fast 3D model draws.

        Flat 16-value matrices are column-major; nested 4x4 matrices are row-major.
        """
        self._compose_transform3d(_coerce_matrix4_payload(matrix))

    def rotate(
        self,
        angle: float | None = None,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 1.0,
        *,
        axis: Sequence[float] | None = None,
        quaternion: Sequence[float] | None = None,
    ) -> None:
        """Rotate by a z angle, axis-angle pair, or ``(w, x, y, z)`` quaternion."""
        if quaternion is not None:
            if angle is not None:
                raise ValueError("rotate() accepts either angle or quaternion, not both.")
            self.rotate_quaternion(*_sequence4(quaternion, name="quaternion"))
            return
        if angle is None:
            raise TypeError("rotate() missing required angle or quaternion.")
        if axis is not None:
            x, y, z = _sequence3(axis, name="axis")
        radians = self._context._angle(float(angle))
        self._compose_transform3d(_mat4_axis_angle(radians, float(x), float(y), float(z)))

    def rotate_x(self, angle: float) -> None:
        """Rotate subsequent fast 3D model draws around the x axis."""
        radians = self._context._angle(float(angle))
        if self._transform3d_active:
            self._transform3d = _mat4_post_rotate_x(self._transform3d, radians)
        else:
            self._transform3d = _mat4_axis_angle(radians, 1.0, 0.0, 0.0)
            self._transform3d_active = True

    def rotate_y(self, angle: float) -> None:
        """Rotate subsequent fast 3D model draws around the y axis."""
        radians = self._context._angle(float(angle))
        if self._transform3d_active:
            self._transform3d = _mat4_post_rotate_y(self._transform3d, radians)
        else:
            self._transform3d = _mat4_axis_angle(radians, 0.0, 1.0, 0.0)
            self._transform3d_active = True

    def rotate_z(self, angle: float) -> None:
        """Rotate subsequent fast 3D model draws around the z axis."""
        radians = self._context._angle(float(angle))
        if self._transform3d_active:
            self._transform3d = _mat4_post_rotate_z(self._transform3d, radians)
        else:
            self._transform3d = _mat4_axis_angle(radians, 0.0, 0.0, 1.0)
            self._transform3d_active = True

    def rotate_quaternion(self, w: float, x: float, y: float, z: float) -> None:
        """Rotate subsequent fast 3D model draws by a ``(w, x, y, z)`` quaternion."""
        rotation = _mat4_quaternion(float(w), float(x), float(y), float(z))
        if self._transform3d_active and _mat4_is_translation(self._transform3d):
            self._transform3d = _mat4_translation_then_rotation(self._transform3d, rotation)
            return
        self._compose_transform3d(rotation)
