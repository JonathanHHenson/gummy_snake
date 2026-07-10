"""Vector and camera-space math helpers for 3D context methods."""

from __future__ import annotations

import math

from gummysnake.drawing.renderer3d import Camera3D, Vec3


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
