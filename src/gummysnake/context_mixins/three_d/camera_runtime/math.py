"""Vector and camera-space math helpers for 3D context methods."""

from __future__ import annotations

import math

from gummysnake.drawing.renderer3d import Camera3D, Vec3
from gummysnake.drawing.renderer3d._math import add as _add
from gummysnake.drawing.renderer3d._math import cross as _cross
from gummysnake.drawing.renderer3d._math import dot as _dot
from gummysnake.drawing.renderer3d._math import length as _length
from gummysnake.drawing.renderer3d._math import normalized_or_none
from gummysnake.drawing.renderer3d._math import scale as _scale
from gummysnake.drawing.renderer3d._math import subtract as _sub


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


def _normalize(value: Vec3) -> Vec3:
    return normalized_or_none(value) or Vec3(0.0, 0.0, 0.0)
