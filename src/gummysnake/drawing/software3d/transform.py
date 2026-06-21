"""Model transforms for software 3D."""

from __future__ import annotations

import math

import numpy as np

from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import Mesh3D, Model3D


def transform_model(model: Model3D, matrix: Matrix2D) -> Model3D:
    """Apply the active sketch transform to model coordinates before projection."""

    if matrix == Matrix2D.identity():
        return model
    z_scale = (math.hypot(matrix.a, matrix.b) + math.hypot(matrix.c, matrix.d)) / 2.0
    transformed_meshes = []
    linear = np.array(
        ((matrix.a, matrix.b, 0.0), (matrix.c, matrix.d, 0.0), (0.0, 0.0, z_scale)),
        dtype=np.float64,
    )
    offset = np.array((matrix.e, -matrix.f, 0.0), dtype=np.float64)
    for mesh in model.meshes:
        vertices = mesh.vertex_array() @ linear + offset
        transformed_meshes.append(
            Mesh3D.from_arrays(
                vertices,
                face_indices=mesh.face_index_array(),
                face_offsets=mesh.face_offset_array(),
                normals=mesh.normal_array(),
                texcoords=mesh.texcoord_array(),
                material=mesh.material,
            )
        )
    return Model3D(meshes=tuple(transformed_meshes), source=model.source)
