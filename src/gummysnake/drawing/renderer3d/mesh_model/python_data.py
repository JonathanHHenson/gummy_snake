# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
"""Mesh storage and conversion helpers for 3D rendering."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TypedDict, cast

from gummysnake.drawing.renderer3d._mesh_buffers import (
    MeshFaceInput,
    MeshFloatInput,
    MeshIndexInput,
    MeshRustHandle,
    coerce_vec2_rows,
    coerce_vec3_rows,
    create_rust_mesh_handle,
    pack_faces,
    resolve_face_buffers,
)
from gummysnake.drawing.renderer3d._numpy import NumpyArray, _readonly_numpy_array
from gummysnake.drawing.renderer3d.materials import Material3D
from gummysnake.drawing.renderer3d.types import Vec3


class MeshPythonData(TypedDict):
    """Dictionary returned by :meth:`Mesh3D.to_python`."""

    vertices: tuple[Vec3, ...]
    faces: tuple[tuple[int, ...], ...]
    normals: tuple[Vec3, ...]
    texcoords: tuple[tuple[float, float], ...]
    material: Material3D | None
    bounding_box: tuple[Vec3, Vec3]
    edges: tuple[tuple[int, int], ...]
