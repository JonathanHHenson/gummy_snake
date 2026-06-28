"""Small math-only prototype for future WEBGL-like projection work.

The prototype does not draw pixels and does not depend on OpenGL. It projects simple
3D mesh wireframes into Gummy Snake logical 2D coordinates so camera and projection semantics
can be tested independently from a concrete native renderer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gummysnake.drawing.renderer3d import (
    Camera3D,
    FrustumProjection,
    Mesh3D,
    Model3D,
    OrthographicProjection,
    PerspectiveProjection,
    Projection3D,
    Vec3,
)

type ScreenPoint = tuple[float, float]


@dataclass(frozen=True, slots=True)
class ProjectedLine:
    """A projected wireframe edge in Gummy Snake logical screen coordinates."""

    start: ScreenPoint
    end: ScreenPoint


def cube_model(size: float = 100.0) -> Model3D:
    """Return a simple indexed cube model centered on the origin.
    
    Args:
        size: The size value. Expected type: `float`. Defaults to `100.0`.
    
    Returns:
        The return value. Type: `Model3D`.
    """

    if size <= 0:
        raise ValueError("cube_model() size must be positive.")
    h = size / 2.0
    vertices = (
        Vec3(-h, -h, -h),
        Vec3(h, -h, -h),
        Vec3(h, h, -h),
        Vec3(-h, h, -h),
        Vec3(-h, -h, h),
        Vec3(h, -h, h),
        Vec3(h, h, h),
        Vec3(-h, h, h),
    )
    faces = (
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (2, 3, 7, 6),
        (1, 2, 6, 5),
        (0, 3, 7, 4),
    )
    return Model3D(meshes=(Mesh3D(vertices=vertices, faces=faces),))


def wireframe_segments(
    model: Model3D,
    camera: Camera3D,
    projection: Projection3D,
    *,
    viewport_width: float,
    viewport_height: float,
) -> list[ProjectedLine]:
    """Project model edges into 2D line segments.
    
    Args:
        model: The model value. Expected type: `Model3D`.
        camera: The camera value. Expected type: `Camera3D`.
        projection: The projection value. Expected type: `Projection3D`.
        viewport_width: The viewport width value. Expected type: `float`.
        viewport_height: The viewport height value. Expected type: `float`.
    
    Returns:
        The return value. Type: `list[ProjectedLine]`.
    """

    if viewport_width <= 0 or viewport_height <= 0:
        raise ValueError("viewport dimensions must be positive.")
    _validate_projection(projection)

    lines: list[ProjectedLine] = []
    for mesh in model.meshes:
        projected = [
            _project_point(vertex, camera, projection, viewport_width, viewport_height)
            for vertex in mesh.vertices
        ]
        for a, b in _mesh_edges(mesh):
            start = projected[a]
            end = projected[b]
            if start is not None and end is not None:
                lines.append(ProjectedLine(start, end))
    return lines


def _mesh_edges(mesh: Mesh3D) -> list[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    for face in mesh.faces:
        if len(face) < 2:
            continue
        for index, start in enumerate(face):
            end = face[(index + 1) % len(face)]
            edge = (start, end) if start < end else (end, start)
            edges.add(edge)
    return sorted(edges)


def _project_point(
    point: Vec3,
    camera: Camera3D,
    projection: Projection3D,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    camera_point = _camera_space(point, camera)
    if isinstance(projection, PerspectiveProjection):
        return _project_perspective(camera_point, projection, viewport_width, viewport_height)
    if isinstance(projection, FrustumProjection):
        return _project_frustum(camera_point, projection, viewport_width, viewport_height)
    return _project_orthographic(camera_point, projection, viewport_width, viewport_height)


def _project_perspective(
    point: Vec3,
    projection: PerspectiveProjection,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    if point.z < projection.near or point.z > projection.far:
        return None
    aspect = projection.aspect or viewport_width / viewport_height
    half_fov = math.radians(projection.fov_y) / 2.0
    scale_y = math.tan(half_fov) * point.z
    scale_x = scale_y * aspect
    x_ndc = point.x / scale_x
    y_ndc = point.y / scale_y
    return _ndc_to_screen(x_ndc, y_ndc, viewport_width, viewport_height)


def _project_frustum(
    point: Vec3,
    projection: FrustumProjection,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint | None:
    if point.z < projection.near or point.z > projection.far or point.z == 0:
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
    if point.z < projection.near or point.z > projection.far:
        return None
    x_ndc = point.x / (projection.width / 2.0)
    y_ndc = point.y / (projection.height / 2.0)
    return _ndc_to_screen(x_ndc, y_ndc, viewport_width, viewport_height)


def _ndc_to_screen(
    x_ndc: float,
    y_ndc: float,
    viewport_width: float,
    viewport_height: float,
) -> ScreenPoint:
    x = (x_ndc + 1.0) * 0.5 * viewport_width
    y = (1.0 - (y_ndc + 1.0) * 0.5) * viewport_height
    return (x, y)


def _camera_space(point: Vec3, camera: Camera3D) -> Vec3:
    forward = _normalize(_sub(camera.target, camera.eye))
    right = _normalize(_cross(forward, camera.up))
    true_up = _cross(right, forward)
    relative = _sub(point, camera.eye)
    return Vec3(_dot(relative, right), _dot(relative, true_up), _dot(relative, forward))


def _validate_projection(projection: Projection3D) -> None:
    if projection.near <= 0:
        raise ValueError("projection near plane must be positive.")
    if projection.far <= projection.near:
        raise ValueError("projection far plane must be greater than the near plane.")
    if isinstance(projection, PerspectiveProjection):
        if projection.fov_y <= 0 or projection.fov_y >= 180:
            raise ValueError("perspective fov_y must be between 0 and 180 degrees.")
        if projection.aspect is not None and projection.aspect <= 0:
            raise ValueError("perspective aspect must be positive when provided.")
    elif isinstance(projection, FrustumProjection):
        if projection.left >= projection.right:
            raise ValueError("frustum left must be less than right.")
        if projection.bottom >= projection.top:
            raise ValueError("frustum bottom must be less than top.")
    elif projection.width <= 0 or projection.height <= 0:
        raise ValueError("orthographic width and height must be positive.")


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)


def _dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def _normalize(value: Vec3) -> Vec3:
    length = math.sqrt(_dot(value, value))
    if length == 0:
        raise ValueError("camera eye/target/up vectors must define a valid orientation.")
    return Vec3(value.x / length, value.y / length, value.z / length)


__all__ = ["ProjectedLine", "ScreenPoint", "cube_model", "wireframe_segments"]
