"""Model transforms for software 3D."""

from __future__ import annotations

import math

from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import Mesh3D, Model3D


def transform_model(model: Model3D, matrix: Matrix2D) -> Model3D:
    """Apply the active sketch transform to model coordinates before projection."""

    if matrix == Matrix2D.identity():
        return model
    z_scale = (math.hypot(matrix.a, matrix.b) + math.hypot(matrix.c, matrix.d)) / 2.0
    transformed_meshes = []
    for mesh in model.meshes:
        vertices = tuple(
            (
                matrix.a * vertex.x + matrix.c * vertex.y + matrix.e,
                matrix.b * vertex.x + matrix.d * vertex.y - matrix.f,
                vertex.z * z_scale,
            )
            for vertex in mesh.vertices
        )
        face_offsets = [0]
        face_indices: list[int] = []
        for face in mesh.faces:
            face_indices.extend(face)
            face_offsets.append(len(face_indices))
        transformed_meshes.append(
            Mesh3D.from_arrays(
                vertices,
                face_indices=face_indices,
                face_offsets=face_offsets,
                normals=tuple((normal.x, normal.y, normal.z) for normal in mesh.normals),
                texcoords=mesh.texcoords,
                material=mesh.material,
            )
        )
    return Model3D(meshes=tuple(transformed_meshes), source=model.source)
