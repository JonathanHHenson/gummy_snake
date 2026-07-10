from __future__ import annotations

import math
from typing import TYPE_CHECKING

from gummysnake.drawing.renderer3d._mesh_buffers import MeshRustHandle
from gummysnake.drawing.renderer3d.types import Vec3

if TYPE_CHECKING:
    from gummysnake.drawing.renderer3d.mesh_model.mesh import Mesh3D


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.x - b.x, a.y - b.y, a.z - b.z)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def _normalize(value: Vec3) -> Vec3:
    length = math.sqrt(value.x * value.x + value.y * value.y + value.z * value.z)
    if length == 0.0:
        return Vec3(0.0, 0.0, 1.0)
    return Vec3(value.x / length, value.y / length, value.z / length)


def _mesh_rust_handle(mesh: Mesh3D) -> MeshRustHandle | None:
    return mesh._rust_handle
