"""Model transforms for software 3D."""

from __future__ import annotations

import math

from gummysnake.core.transform import Matrix2D
from gummysnake.drawing.renderer3d import Mesh3D, Model3D, Vec3


def transform_model(model: Model3D, matrix: Matrix2D) -> Model3D:
    """Apply the active sketch transform to model coordinates before projection."""

    if matrix == Matrix2D.identity():
        return model
    z_scale = (math.hypot(matrix.a, matrix.b) + math.hypot(matrix.c, matrix.d)) / 2.0
    transformed_meshes = []
    for mesh in model.meshes:
        vertices = []
        for vertex in mesh.vertices:
            x = matrix.a * vertex.x + matrix.c * vertex.y + matrix.e
            y = matrix.b * vertex.x + matrix.d * vertex.y - matrix.f
            vertices.append(Vec3(x, y, vertex.z * z_scale))
        transformed_meshes.append(
            Mesh3D(
                vertices=tuple(vertices),
                faces=mesh.faces,
                normals=mesh.normals,
                texcoords=mesh.texcoords,
                material=mesh.material,
            )
        )
    return Model3D(meshes=tuple(transformed_meshes), source=model.source)
