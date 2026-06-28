"""3D camera and projection methods for SketchContext."""

from __future__ import annotations

import math
from typing import Any, cast, overload

from gummysnake.context_mixins.three_d._protocols import ThreeDContextHost
from gummysnake.drawing.renderer3d import (
    Camera3D,
    FrustumProjection,
    OrthographicProjection,
    PerspectiveProjection,
    Vec3,
)
from gummysnake.exceptions import ArgumentValidationError

Number = int | float


def _three_d(self: Any) -> ThreeDContextHost:
    return cast(ThreeDContextHost, self)


class ThreeDCameraMixin:
    state: Any
    _camera3d: Camera3D
    _projection3d: PerspectiveProjection | OrthographicProjection | FrustumProjection
    _frame_mouse_dx: float
    _frame_mouse_dy: float
    _frame_scroll_x: float
    _frame_scroll_y: float

    @property
    def width(self) -> int:
        """Width.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        raise NotImplementedError

    @property
    def height(self) -> int:
        """Height.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        raise NotImplementedError

    @overload
    def create_camera(self) -> Camera3D:
        """Overload accepting no camera, an existing camera, or camera basis values.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        ...

    @overload
    def create_camera(self, camera: Camera3D, /) -> Camera3D:
        """Overload accepting no camera, an existing camera, or camera basis values.
        
        Args:
            camera: The camera value. Expected type: `Camera3D`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        ...

    @overload
    def create_camera(
        self,
        eye_x: Number,
        eye_y: Number,
        eye_z: Number,
        center_x: Number,
        center_y: Number,
        center_z: Number,
        up_x: Number,
        up_y: Number,
        up_z: Number,
        /,
    ) -> Camera3D:
        """Overload accepting no camera, an existing camera, or camera basis values.
        
        Args:
            eye_x: The eye x value. Expected type: `Number`.
            eye_y: The eye y value. Expected type: `Number`.
            eye_z: The eye z value. Expected type: `Number`.
            center_x: The center x value. Expected type: `Number`.
            center_y: The center y value. Expected type: `Number`.
            center_z: The center z value. Expected type: `Number`.
            up_x: The up x value. Expected type: `Number`.
            up_y: The up y value. Expected type: `Number`.
            up_z: The up z value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        ...

    def create_camera(self, *args: Any) -> Camera3D:
        """Create camera.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        return self.camera(*args)

    @overload
    def camera(self) -> Camera3D:
        """Overload accepting no camera, an existing camera, or camera basis values.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        ...

    @overload
    def camera(self, camera: Camera3D, /) -> Camera3D:
        """Overload accepting no camera, an existing camera, or camera basis values.
        
        Args:
            camera: The camera value. Expected type: `Camera3D`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        ...

    @overload
    def camera(
        self,
        eye_x: Number,
        eye_y: Number,
        eye_z: Number,
        center_x: Number,
        center_y: Number,
        center_z: Number,
        up_x: Number,
        up_y: Number,
        up_z: Number,
        /,
    ) -> Camera3D:
        """Overload accepting no camera, an existing camera, or camera basis values.
        
        Args:
            eye_x: The eye x value. Expected type: `Number`.
            eye_y: The eye y value. Expected type: `Number`.
            eye_z: The eye z value. Expected type: `Number`.
            center_x: The center x value. Expected type: `Number`.
            center_y: The center y value. Expected type: `Number`.
            center_z: The center z value. Expected type: `Number`.
            up_x: The up x value. Expected type: `Number`.
            up_y: The up y value. Expected type: `Number`.
            up_z: The up z value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        ...

    def camera(self, *args: Any) -> Camera3D:
        """Camera.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
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

    def set_camera(self, camera: Camera3D) -> Camera3D:
        """Set camera.
        
        Args:
            camera: The camera value. Expected type: `Camera3D`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        _three_d(self)._require_webgl_mode("set_camera")
        if not isinstance(camera, Camera3D):
            raise ArgumentValidationError("set_camera() requires a Camera3D value.")
        self._camera3d = camera
        return camera

    def roll(self, angle: Number) -> Camera3D:
        """Roll.
        
        Args:
            angle: The angle value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        _three_d(self)._require_webgl_mode("roll")
        radians = _three_d(self)._angle(float(angle))
        forward, _right, true_up = _camera_basis(self._camera3d)
        new_up = _rotate_around_axis(true_up, forward, radians)
        self._camera3d = Camera3D(eye=self._camera3d.eye, target=self._camera3d.target, up=new_up)
        return self._camera3d

    @overload
    def perspective(self) -> PerspectiveProjection:
        """Overload accepting optional perspective projection values.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `PerspectiveProjection`.
        """
        ...

    @overload
    def perspective(self, fov: Number, /) -> PerspectiveProjection:
        """Overload accepting optional perspective projection values.
        
        Args:
            fov: The fov value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `PerspectiveProjection`.
        """
        ...

    @overload
    def perspective(self, fov: Number, aspect: Number, /) -> PerspectiveProjection:
        """Overload accepting optional perspective projection values.
        
        Args:
            fov: The fov value. Expected type: `Number`.
            aspect: The aspect value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `PerspectiveProjection`.
        """
        ...

    @overload
    def perspective(
        self, fov: Number, aspect: Number, near: Number, /
    ) -> PerspectiveProjection:
        """Overload accepting optional perspective projection values.
        
        Args:
            fov: The fov value. Expected type: `Number`.
            aspect: The aspect value. Expected type: `Number`.
            near: The near value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `PerspectiveProjection`.
        """
        ...

    @overload
    def perspective(
        self, fov: Number, aspect: Number, near: Number, far: Number, /
    ) -> PerspectiveProjection:
        """Overload accepting optional perspective projection values.
        
        Args:
            fov: The fov value. Expected type: `Number`.
            aspect: The aspect value. Expected type: `Number`.
            near: The near value. Expected type: `Number`.
            far: The far value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `PerspectiveProjection`.
        """
        ...

    def perspective(self, *args: Any) -> PerspectiveProjection:
        """Perspective.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            The return value. Type: `PerspectiveProjection`.
        """
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

    @overload
    def ortho(self) -> OrthographicProjection:
        """Overload accepting optional orthographic projection values.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `OrthographicProjection`.
        """
        ...

    @overload
    def ortho(self, width: Number, height: Number, /) -> OrthographicProjection:
        """Overload accepting optional orthographic projection values.
        
        Args:
            width: The width value. Expected type: `Number`.
            height: The height value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `OrthographicProjection`.
        """
        ...

    @overload
    def ortho(
        self, width: Number, height: Number, near: Number, far: Number, /
    ) -> OrthographicProjection:
        """Overload accepting optional orthographic projection values.
        
        Args:
            width: The width value. Expected type: `Number`.
            height: The height value. Expected type: `Number`.
            near: The near value. Expected type: `Number`.
            far: The far value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `OrthographicProjection`.
        """
        ...

    def ortho(self, *args: Any) -> OrthographicProjection:
        """Ortho.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            The return value. Type: `OrthographicProjection`.
        """
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

    def frustum(
        self,
        left: Number,
        right: Number,
        bottom: Number,
        top: Number,
        near: Number = 0.1,
        far: Number = 10_000.0,
    ) -> FrustumProjection:
        """Frustum.
        
        Args:
            left: The left value. Expected type: `Number`.
            right: The right value. Expected type: `Number`.
            bottom: The bottom value. Expected type: `Number`.
            top: The top value. Expected type: `Number`.
            near: The near value. Expected type: `Number`. Defaults to `0.1`.
            far: The far value. Expected type: `Number`. Defaults to `10000.0`.
        
        Returns:
            The return value. Type: `FrustumProjection`.
        """
        _three_d(self)._require_webgl_mode("frustum")
        projection = FrustumProjection(
            left=float(left),
            right=float(right),
            bottom=float(bottom),
            top=float(top),
            near=float(near),
            far=float(far),
        )
        if projection.near <= 0 or projection.far <= projection.near:
            raise ArgumentValidationError("frustum() requires 0 < near < far.")
        if projection.left >= projection.right or projection.bottom >= projection.top:
            raise ArgumentValidationError("frustum() requires left < right and bottom < top.")
        self._projection3d = projection
        return projection

    def world_to_screen(self, x: Number, y: Number, z: Number) -> tuple[float, float, float]:
        """World to screen.
        
        Args:
            x: The x value. Expected type: `Number`.
            y: The y value. Expected type: `Number`.
            z: The z value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `tuple[float, float, float]`.
        """
        _three_d(self)._require_webgl_mode("world_to_screen")
        camera_point = _world_to_camera(Vec3(float(x), float(y), float(z)), self._camera3d)
        projection = self._projection3d
        if isinstance(projection, PerspectiveProjection):
            aspect = projection.aspect or max(1.0, float(self.width)) / max(1.0, float(self.height))
            half_fov = math.radians(projection.fov_y) / 2.0
            scale_y = math.tan(half_fov) * camera_point.z
            scale_x = scale_y * aspect
            x_ndc = 0.0 if scale_x == 0 else camera_point.x / scale_x
            y_ndc = 0.0 if scale_y == 0 else camera_point.y / scale_y
            near, far = projection.near, projection.far
        elif isinstance(projection, FrustumProjection):
            x_near = camera_point.x * projection.near / camera_point.z
            y_near = camera_point.y * projection.near / camera_point.z
            x_ndc = ((x_near - projection.left) / (projection.right - projection.left)) * 2.0 - 1.0
            y_ndc = (
                (y_near - projection.bottom) / (projection.top - projection.bottom)
            ) * 2.0 - 1.0
            near, far = projection.near, projection.far
        else:
            x_ndc = camera_point.x / (projection.width / 2.0)
            y_ndc = camera_point.y / (projection.height / 2.0)
            near, far = projection.near, projection.far
        screen_x = (x_ndc + 1.0) * 0.5 * float(self.width)
        screen_y = (1.0 - (y_ndc + 1.0) * 0.5) * float(self.height)
        depth = 0.0 if far == near else (camera_point.z - near) / (far - near)
        return (screen_x, screen_y, depth)

    def screen_to_world(self, x: Number, y: Number, depth: Number = 0.0) -> Vec3:
        """Screen to world.
        
        Args:
            x: The x value. Expected type: `Number`.
            y: The y value. Expected type: `Number`.
            depth: The depth value. Expected type: `Number`. Defaults to `0.0`.
        
        Returns:
            The return value. Type: `Vec3`.
        """
        _three_d(self)._require_webgl_mode("screen_to_world")
        x_ndc = (float(x) / max(1.0, float(self.width))) * 2.0 - 1.0
        y_ndc = 1.0 - (float(y) / max(1.0, float(self.height))) * 2.0
        projection = self._projection3d
        normalized_depth = max(0.0, min(1.0, float(depth)))
        near = projection.near
        far = projection.far
        distance = near + (far - near) * normalized_depth
        if isinstance(projection, PerspectiveProjection):
            aspect = projection.aspect or max(1.0, float(self.width)) / max(1.0, float(self.height))
            half_fov = math.radians(projection.fov_y) / 2.0
            camera_point = Vec3(
                x_ndc * math.tan(half_fov) * aspect * distance,
                y_ndc * math.tan(half_fov) * distance,
                distance,
            )
        elif isinstance(projection, FrustumProjection):
            near_x = projection.left + (x_ndc + 1.0) * 0.5 * (projection.right - projection.left)
            near_y = projection.bottom + (y_ndc + 1.0) * 0.5 * (projection.top - projection.bottom)
            scale = distance / projection.near
            camera_point = Vec3(near_x * scale, near_y * scale, distance)
        else:
            camera_point = Vec3(
                x_ndc * projection.width / 2.0,
                y_ndc * projection.height / 2.0,
                distance,
            )
        return _camera_to_world(camera_point, self._camera3d)

    @overload
    def orbit_control(self) -> Camera3D:
        """Overload accepting optional orbit-control sensitivities.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        ...

    @overload
    def orbit_control(self, sensitivity_x: Number, /) -> Camera3D:
        """Overload accepting optional orbit-control sensitivities.
        
        Args:
            sensitivity_x: The sensitivity x value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        ...

    @overload
    def orbit_control(self, sensitivity_x: Number, sensitivity_y: Number, /) -> Camera3D:
        """Overload accepting optional orbit-control sensitivities.
        
        Args:
            sensitivity_x: The sensitivity x value. Expected type: `Number`.
            sensitivity_y: The sensitivity y value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        ...

    @overload
    def orbit_control(
        self, sensitivity_x: Number, sensitivity_y: Number, sensitivity_z: Number, /
    ) -> Camera3D:
        """Overload accepting optional orbit-control sensitivities.
        
        Args:
            sensitivity_x: The sensitivity x value. Expected type: `Number`.
            sensitivity_y: The sensitivity y value. Expected type: `Number`.
            sensitivity_z: The sensitivity z value. Expected type: `Number`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
        ...

    def orbit_control(self, *args: Any) -> Camera3D:
        """Orbit control.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
        
        Returns:
            The return value. Type: `Camera3D`.
        """
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


def _camera_basis(camera: Camera3D) -> tuple[Vec3, Vec3, Vec3]:
    forward = _normalize(_sub(camera.target, camera.eye))
    right = _normalize(_cross(forward, camera.up))
    if _length(right) == 0.0:
        right = Vec3(1.0, 0.0, 0.0)
    true_up = _normalize(_cross(right, forward))
    return forward, right, true_up


def _world_to_camera(point: Vec3, camera: Camera3D) -> Vec3:
    forward, right, true_up = _camera_basis(camera)
    relative = _sub(point, camera.eye)
    return Vec3(_dot(relative, right), _dot(relative, true_up), _dot(relative, forward))


def _camera_to_world(point: Vec3, camera: Camera3D) -> Vec3:
    forward, right, true_up = _camera_basis(camera)
    return _add(
        camera.eye,
        _add(_scale(right, point.x), _add(_scale(true_up, point.y), _scale(forward, point.z))),
    )


def _rotate_around_axis(vector: Vec3, axis: Vec3, angle: float) -> Vec3:
    axis = _normalize(axis)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return _add(
        _add(_scale(vector, cos_a), _scale(_cross(axis, vector), sin_a)),
        _scale(axis, _dot(axis, vector) * (1.0 - cos_a)),
    )


def _add(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x + b.x, a.y + b.y, a.z + b.z)


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)


def _scale(value: Vec3, scalar: float) -> Vec3:
    return Vec3(value.x * scalar, value.y * scalar, value.z * scalar)


def _dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def _length(value: Vec3) -> float:
    return math.sqrt(_dot(value, value))


def _normalize(value: Vec3) -> Vec3:
    length = _length(value)
    if length == 0.0:
        return Vec3(0.0, 0.0, 0.0)
    return _scale(value, 1.0 / length)
