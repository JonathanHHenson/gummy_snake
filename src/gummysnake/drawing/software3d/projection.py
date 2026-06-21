"""Camera and projection helpers for software 3D."""

from __future__ import annotations

import math

from gummysnake.drawing.renderer3d import (
    Camera3D,
    OrthographicProjection,
    PerspectiveProjection,
    Projection3D,
    Vec3,
)
from gummysnake.exceptions import ArgumentValidationError

from .math3d import cross, dot, normalize, sub
from .types import ScreenPoint


def visible(point: Vec3, projection: Projection3D) -> bool:
    return projection.near <= point.z <= projection.far


def project_camera_point(
    point: Vec3,
    projection: Projection3D,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    if isinstance(projection, PerspectiveProjection):
        return _project_perspective(point, projection, viewport_width, viewport_height)
    return _project_orthographic(point, projection, viewport_width, viewport_height)


def camera_space(point: Vec3, camera: Camera3D) -> Vec3:
    forward = normalize(sub(camera.target, camera.eye))
    right = normalize(cross(forward, camera.up))
    true_up = cross(right, forward)
    relative = sub(point, camera.eye)
    return Vec3(dot(relative, right), dot(relative, true_up), dot(relative, forward))


def validate_projection(projection: Projection3D) -> None:
    if projection.near <= 0:
        raise ArgumentValidationError("projection near plane must be positive.")
    if projection.far <= projection.near:
        raise ArgumentValidationError("projection far plane must be greater than the near plane.")
    if isinstance(projection, PerspectiveProjection):
        if projection.fov_y <= 0 or projection.fov_y >= 180:
            raise ArgumentValidationError("perspective fov_y must be between 0 and 180 degrees.")
        if projection.aspect is not None and projection.aspect <= 0:
            raise ArgumentValidationError("perspective aspect must be positive when provided.")
    elif projection.width <= 0 or projection.height <= 0:
        raise ArgumentValidationError("orthographic width and height must be positive.")


def _project_perspective(
    point: Vec3,
    projection: PerspectiveProjection,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    if not visible(point, projection):
        return None
    aspect = projection.aspect or viewport_width / viewport_height
    half_fov = math.radians(projection.fov_y) / 2.0
    scale_y = math.tan(half_fov) * point.z
    if scale_y == 0:
        return None
    scale_x = scale_y * aspect
    if scale_x == 0:
        return None
    return _ndc_to_screen(point.x / scale_x, point.y / scale_y, viewport_width, viewport_height)


def _project_orthographic(
    point: Vec3,
    projection: OrthographicProjection,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    if not visible(point, projection):
        return None
    return _ndc_to_screen(
        point.x / (projection.width / 2.0),
        point.y / (projection.height / 2.0),
        viewport_width,
        viewport_height,
    )


def _ndc_to_screen(
    x_ndc: float, y_ndc: float, viewport_width: float, viewport_height: float
) -> ScreenPoint:
    return ((x_ndc + 1.0) * 0.5 * viewport_width, (1.0 - (y_ndc + 1.0) * 0.5) * viewport_height)
