"""3D camera and projection methods for SketchContext."""

from __future__ import annotations

import math
from typing import Any, cast

from gummysnake._context.three_d._protocols import ThreeDContextHost
from gummysnake.drawing.renderer3d import (
    Camera3D,
    OrthographicProjection,
    PerspectiveProjection,
    Vec3,
)
from gummysnake.exceptions import ArgumentValidationError


def _three_d(self: object) -> ThreeDContextHost:
    return cast(ThreeDContextHost, self)


class ThreeDCameraMixin:
    state: Any
    _camera3d: Camera3D
    _projection3d: PerspectiveProjection | OrthographicProjection
    _frame_mouse_dx: float
    _frame_mouse_dy: float
    _frame_scroll_x: float
    _frame_scroll_y: float

    @property
    def width(self) -> int:
        raise NotImplementedError

    @property
    def height(self) -> int:
        raise NotImplementedError

    def create_camera(self, *args: object) -> Camera3D:
        return self.camera(*args)

    def camera(self, *args: object) -> Camera3D:
        _three_d(self)._require_webgl_mode("camera")
        if len(args) == 0:
            camera = Camera3D()
        elif len(args) == 1 and isinstance(args[0], Camera3D):
            camera = args[0]
        elif len(args) == 9 and all(isinstance(value, int | float) for value in args):
            numeric_args = _three_d(self)._numeric_values(args)
            camera = Camera3D(
                eye=Vec3(numeric_args[0], numeric_args[1], numeric_args[2]),
                target=Vec3(numeric_args[3], numeric_args[4], numeric_args[5]),
                up=Vec3(numeric_args[6], numeric_args[7], numeric_args[8]),
            )
        else:
            raise ArgumentValidationError(
                "camera() accepts no arguments, a Camera3D, or nine numeric values."
            )
        self._camera3d = camera
        return camera

    def perspective(self, *args: object) -> PerspectiveProjection:
        _three_d(self)._require_webgl_mode("perspective")
        if len(args) > 4 or not all(isinstance(value, int | float) for value in args):
            raise ArgumentValidationError(
                "perspective() accepts fov, aspect, near, and far numeric values."
            )
        numeric_args = _three_d(self)._numeric_values(args)
        fov_y = (
            60.0 if len(numeric_args) == 0 else math.degrees(_three_d(self)._angle(numeric_args[0]))
        )
        aspect = None if len(numeric_args) < 2 else numeric_args[1]
        near = 0.1 if len(numeric_args) < 3 else numeric_args[2]
        far = 10_000.0 if len(numeric_args) < 4 else numeric_args[3]
        projection = PerspectiveProjection(fov_y=fov_y, aspect=aspect, near=near, far=far)
        self._projection3d = projection
        return projection

    def ortho(self, *args: object) -> OrthographicProjection:
        _three_d(self)._require_webgl_mode("ortho")
        if len(args) not in {0, 2, 4} or not all(isinstance(value, int | float) for value in args):
            raise ArgumentValidationError(
                "ortho() accepts no arguments, width/height, or width/height/near/far."
            )
        numeric_args = _three_d(self)._numeric_values(args)
        ortho_width = float(self.width) if len(numeric_args) == 0 else numeric_args[0]
        ortho_height = float(self.height) if len(numeric_args) == 0 else numeric_args[1]
        near = 0.1 if len(numeric_args) < 4 else numeric_args[2]
        far = 10_000.0 if len(numeric_args) < 4 else numeric_args[3]
        projection = OrthographicProjection(
            width=ortho_width, height=ortho_height, near=near, far=far
        )
        self._projection3d = projection
        return projection

    def orbit_control(self, *args: object) -> Camera3D:
        _three_d(self)._require_webgl_mode("orbit_control")
        if len(args) > 3 or not all(isinstance(value, int | float) for value in args):
            raise ArgumentValidationError(
                "orbit_control() accepts up to three numeric sensitivity values."
            )
        numeric_args = _three_d(self)._numeric_values(args)
        sensitivity_x = 1.0 if len(numeric_args) == 0 else numeric_args[0]
        sensitivity_y = sensitivity_x if len(numeric_args) < 2 else numeric_args[1]
        sensitivity_z = 1.0 if len(numeric_args) < 3 else numeric_args[2]
        if sensitivity_x <= 0 or sensitivity_y <= 0 or sensitivity_z <= 0:
            raise ArgumentValidationError("orbit_control() sensitivities must be positive.")

        offset = Vec3(
            self._camera3d.eye.x - self._camera3d.target.x,
            self._camera3d.eye.y - self._camera3d.target.y,
            self._camera3d.eye.z - self._camera3d.target.z,
        )
        radius = math.sqrt(offset.x * offset.x + offset.y * offset.y + offset.z * offset.z)
        if radius <= 0:
            raise ArgumentValidationError("orbit_control() requires a non-zero camera distance.")

        azimuth = math.atan2(offset.x, offset.z)
        polar = math.acos(max(-1.0, min(1.0, offset.y / radius)))
        if self.state.input.mouse_is_pressed:
            azimuth -= self._frame_mouse_dx * 0.01 * sensitivity_x
            polar = max(
                1e-3, min(math.pi - 1e-3, polar + self._frame_mouse_dy * 0.01 * sensitivity_y)
            )
        if self._frame_scroll_y != 0.0:
            radius = max(1.0, radius * math.exp(-self._frame_scroll_y * 0.1 * sensitivity_z))

        sin_polar = math.sin(polar)
        new_eye = Vec3(
            self._camera3d.target.x + radius * sin_polar * math.sin(azimuth),
            self._camera3d.target.y + radius * math.cos(polar),
            self._camera3d.target.z + radius * sin_polar * math.cos(azimuth),
        )
        self._camera3d = Camera3D(eye=new_eye, target=self._camera3d.target, up=Vec3(0.0, 1.0, 0.0))
        self._frame_mouse_dx = 0.0
        self._frame_mouse_dy = 0.0
        self._frame_scroll_x = 0.0
        self._frame_scroll_y = 0.0
        return self._camera3d
