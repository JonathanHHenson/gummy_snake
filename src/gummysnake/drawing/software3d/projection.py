"""Camera and projection helpers for software 3D."""

from __future__ import annotations

import math

from gummysnake.drawing.renderer3d import (
    Camera3D,
    FrustumProjection,
    OrthographicProjection,
    PerspectiveProjection,
    Projection3D,
    Vec3,
)
from gummysnake.exceptions import ArgumentValidationError

from .math3d import cross, dot, normalize, sub
from .types import ScreenPoint


def visible(point: Vec3, projection: Projection3D) -> bool:
    """Visible.
    
    Args:
        point: The point value. Expected type: `Vec3`.
        projection: The projection value. Expected type: `Projection3D`.
    
    Returns:
        The return value. Type: `bool`.
    """
    return projection.near <= point.z <= projection.far


def project_camera_point(
    point: Vec3,
    projection: Projection3D,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    """Project camera point.
    
    Args:
        point: The point value. Expected type: `Vec3`.
        projection: The projection value. Expected type: `Projection3D`.
        viewport_width: The viewport width value. Expected type: `float`.
        viewport_height: The viewport height value. Expected type: `float`.
    
    Returns:
        The return value. Type: `ScreenPoint | None`.
    """
    if isinstance(projection, PerspectiveProjection):
        return _project_perspective(point, projection, viewport_width, viewport_height)
    if isinstance(projection, FrustumProjection):
        return _project_frustum(point, projection, viewport_width, viewport_height)
    return _project_orthographic(point, projection, viewport_width, viewport_height)


def camera_space(point: Vec3, camera: Camera3D) -> Vec3:
    """Camera space.
    
    Args:
        point: The point value. Expected type: `Vec3`.
        camera: The camera value. Expected type: `Camera3D`.
    
    Returns:
        The return value. Type: `Vec3`.
    """
    forward = normalize(sub(camera.target, camera.eye))
    right = normalize(cross(forward, camera.up))
    true_up = cross(right, forward)
    relative = sub(point, camera.eye)
    return Vec3(dot(relative, right), dot(relative, true_up), dot(relative, forward))


def validate_projection(projection: Projection3D) -> None:
    """Validate projection.
    
    Args:
        projection: The projection value. Expected type: `Projection3D`.
    
    Returns:
        None.
    """
    if projection.near <= 0:
        raise ArgumentValidationError("projection near plane must be positive.")
    if projection.far <= projection.near:
        raise ArgumentValidationError("projection far plane must be greater than the near plane.")
    if isinstance(projection, PerspectiveProjection):
        if projection.fov_y <= 0 or projection.fov_y >= 180:
            raise ArgumentValidationError("perspective fov_y must be between 0 and 180 degrees.")
        if projection.aspect is not None and projection.aspect <= 0:
            raise ArgumentValidationError("perspective aspect must be positive when provided.")
    elif isinstance(projection, FrustumProjection):
        if projection.left >= projection.right:
            raise ArgumentValidationError("frustum left must be less than right.")
        if projection.bottom >= projection.top:
            raise ArgumentValidationError("frustum bottom must be less than top.")
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


def _project_frustum(
    point: Vec3,
    projection: FrustumProjection,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    if not visible(point, projection):
        return None
    if point.z == 0:
        return None
    x_near = point.x * projection.near / point.z
    y_near = point.y * projection.near / point.z
    x_ndc = ((x_near - projection.left) / (projection.right - projection.left)) * 2.0 - 1.0
    y_ndc = ((y_near - projection.bottom) / (projection.top - projection.bottom)) * 2.0 - 1.0
    return _ndc_to_screen(x_ndc, y_ndc, viewport_width, viewport_height)


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
