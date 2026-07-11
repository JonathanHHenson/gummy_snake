"""Pure geometry operations for :class:`~gummysnake.drawing.renderer3d.Mesh3D`."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from gummysnake.drawing.renderer3d._math import cross, normalized_or_none, subtract
from gummysnake.drawing.renderer3d._mesh_buffers import MeshRustHandle
from gummysnake.drawing.renderer3d.types import Vec3

if TYPE_CHECKING:
    from gummysnake.drawing.renderer3d.mesh_model.mesh import Mesh3D


def _sub(a: Vec3, b: Vec3) -> Vec3:
    """Compatibility helper for mesh normal calculations."""
    return subtract(a, b)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    """Compatibility helper for mesh normal calculations."""
    return cross(a, b)


def _normalize(value: Vec3) -> Vec3:
    """Return a normal vector, defaulting degenerate values to positive Z."""
    return normalized_or_none(value) or Vec3(0.0, 0.0, 1.0)


def mesh_bounding_box(vertices: Sequence[Vec3]) -> tuple[Vec3, Vec3]:
    """Return axis-aligned logical-coordinate bounds for mesh vertices."""
    if not vertices:
        origin = Vec3(0.0, 0.0, 0.0)
        return origin, origin
    return (
        Vec3(
            min(vertex.x for vertex in vertices),
            min(vertex.y for vertex in vertices),
            min(vertex.z for vertex in vertices),
        ),
        Vec3(
            max(vertex.x for vertex in vertices),
            max(vertex.y for vertex in vertices),
            max(vertex.z for vertex in vertices),
        ),
    )


def mesh_edges(faces: Sequence[Sequence[int]]) -> tuple[tuple[int, int], ...]:
    """Return sorted, unique undirected mesh edges."""
    edges: set[tuple[int, int]] = set()
    for face in faces:
        if len(face) < 2:
            continue
        for start, end in zip(face, (*face[1:], face[0]), strict=True):
            edges.add((min(start, end), max(start, end)))
    return tuple(sorted(edges))


def normalized_vertices(vertices: Sequence[Vec3], size: float) -> tuple[Vec3, ...]:
    """Center and uniformly scale vertices to the requested largest extent."""
    min_corner, max_corner = mesh_bounding_box(vertices)
    center = Vec3(
        (min_corner.x + max_corner.x) / 2.0,
        (min_corner.y + max_corner.y) / 2.0,
        (min_corner.z + max_corner.z) / 2.0,
    )
    extent = max(
        max_corner.x - min_corner.x,
        max_corner.y - min_corner.y,
        max_corner.z - min_corner.z,
        1e-12,
    )
    scale = float(size) / extent
    return tuple(
        Vec3(
            (vertex.x - center.x) * scale,
            (vertex.y - center.y) * scale,
            (vertex.z - center.z) * scale,
        )
        for vertex in vertices
    )


def flipped_texcoords(
    texcoords: Sequence[tuple[float, float]], *, axis: str
) -> tuple[tuple[float, float], ...]:
    """Return texture coordinates mirrored around the selected normalized axis."""
    if axis == "u":
        return tuple((1.0 - u, v) for u, v in texcoords)
    return tuple((u, 1.0 - v) for u, v in texcoords)


def face_normals(vertices: Sequence[Vec3], faces: Sequence[Sequence[int]]) -> tuple[Vec3, ...]:
    """Compute one normal per face, retaining the public degenerate default."""
    normals: list[Vec3] = []
    for face in faces:
        if len(face) < 3:
            normals.append(Vec3(0.0, 0.0, 1.0))
            continue
        a, b, c = vertices[face[0]], vertices[face[1]], vertices[face[2]]
        normals.append(_normalize(_cross(_sub(b, a), _sub(c, a))))
    return tuple(normals)


def averaged_vertex_normals(
    vertices: Sequence[Vec3], faces: Sequence[Sequence[int]]
) -> tuple[Vec3, ...]:
    """Compute averaged vertex normals using the established degenerate default."""
    normals = face_normals(vertices, faces)
    vertex_normals = [Vec3(0.0, 0.0, 0.0) for _ in vertices]
    counts = [0 for _ in vertices]
    for face, normal in zip(faces, normals, strict=True):
        for index in face:
            vertex_normals[index] = Vec3(
                vertex_normals[index].x + normal.x,
                vertex_normals[index].y + normal.y,
                vertex_normals[index].z + normal.z,
            )
            counts[index] += 1
    return tuple(
        _normalize(
            Vec3(
                normal.x / max(1, counts[index]),
                normal.y / max(1, counts[index]),
                normal.z / max(1, counts[index]),
            )
        )
        for index, normal in enumerate(vertex_normals)
    )


def _mesh_rust_handle(mesh: Mesh3D) -> MeshRustHandle | None:
    """Return the mesh's retained Rust handle without materializing buffers."""
    return mesh._rust_handle
