"""Lazy Python and NumPy inspection views for Rust-owned 3D meshes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from gummysnake.drawing.renderer3d._mesh_buffers import MeshRustHandle, faces_from_buffers
from gummysnake.drawing.renderer3d._numpy import NumpyArray, _readonly_numpy_array
from gummysnake.drawing.renderer3d.materials import Material3D
from gummysnake.drawing.renderer3d.mesh_model.storage import MeshBufferData, hydrate_mesh_buffers
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


@dataclass(slots=True)
class MeshPythonCache:
    """Lazy immutable inspection views associated with one Rust mesh handle."""

    buffers: MeshBufferData | None = None
    vertices: tuple[Vec3, ...] | None = None
    faces: tuple[tuple[int, ...], ...] | None = None
    normals: tuple[Vec3, ...] | None = None
    texcoords: tuple[tuple[float, float], ...] | None = None


def ensure_mesh_buffers(cache: MeshPythonCache, handle: MeshRustHandle | None) -> MeshBufferData:
    """Return cached inspection buffers, hydrating the Rust handle once if needed."""
    if cache.buffers is None:
        if handle is None:
            raise RuntimeError("Mesh3D has no Rust canvas mesh handle.")
        cache.buffers = hydrate_mesh_buffers(handle)
    return cache.buffers


def mesh_vertices(cache: MeshPythonCache, handle: MeshRustHandle | None) -> tuple[Vec3, ...]:
    """Return the cached immutable vertex view."""
    buffers = ensure_mesh_buffers(cache, handle)
    if cache.vertices is None:
        cache.vertices = tuple(Vec3(x, y, z) for x, y, z in buffers.vertices)
    return cache.vertices


def mesh_faces(
    cache: MeshPythonCache, handle: MeshRustHandle | None
) -> tuple[tuple[int, ...], ...]:
    """Return the cached immutable face view."""
    buffers = ensure_mesh_buffers(cache, handle)
    if cache.faces is None:
        cache.faces = tuple(faces_from_buffers(buffers.face_indices, buffers.face_offsets))
    return cache.faces


def mesh_normals(cache: MeshPythonCache, handle: MeshRustHandle | None) -> tuple[Vec3, ...]:
    """Return the cached immutable normal view."""
    buffers = ensure_mesh_buffers(cache, handle)
    if cache.normals is None:
        cache.normals = tuple(Vec3(x, y, z) for x, y, z in buffers.normals)
    return cache.normals


def mesh_texcoords(
    cache: MeshPythonCache, handle: MeshRustHandle | None
) -> tuple[tuple[float, float], ...]:
    """Return the cached immutable texture-coordinate view."""
    buffers = ensure_mesh_buffers(cache, handle)
    if cache.texcoords is None:
        cache.texcoords = buffers.texcoords
    return cache.texcoords


def vertex_array(
    cache: MeshPythonCache, handle: MeshRustHandle | None, *, copy: bool
) -> NumpyArray:
    """Return the vertex buffer as an optional NumPy inspection array."""
    return _readonly_numpy_array(
        ensure_mesh_buffers(cache, handle).vertices, dtype="float64", copy=copy
    )


def normal_array(
    cache: MeshPythonCache, handle: MeshRustHandle | None, *, copy: bool
) -> NumpyArray:
    """Return the normal buffer as an optional NumPy inspection array."""
    return _readonly_numpy_array(
        ensure_mesh_buffers(cache, handle).normals, dtype="float64", copy=copy
    )


def texcoord_array(
    cache: MeshPythonCache, handle: MeshRustHandle | None, *, copy: bool
) -> NumpyArray:
    """Return texture coordinates as an optional NumPy inspection array."""
    return _readonly_numpy_array(
        ensure_mesh_buffers(cache, handle).texcoords, dtype="float64", copy=copy
    )


def face_index_array(
    cache: MeshPythonCache, handle: MeshRustHandle | None, *, copy: bool
) -> NumpyArray:
    """Return packed face indices as an optional NumPy inspection array."""
    return _readonly_numpy_array(
        ensure_mesh_buffers(cache, handle).face_indices, dtype="int64", copy=copy
    )


def face_offset_array(
    cache: MeshPythonCache, handle: MeshRustHandle | None, *, copy: bool
) -> NumpyArray:
    """Return packed face offsets as an optional NumPy inspection array."""
    return _readonly_numpy_array(
        ensure_mesh_buffers(cache, handle).face_offsets, dtype="int64", copy=copy
    )


def mesh_python_data(
    *,
    vertices: tuple[Vec3, ...],
    faces: tuple[tuple[int, ...], ...],
    normals: tuple[Vec3, ...],
    texcoords: tuple[tuple[float, float], ...],
    material: Material3D | None,
    bounding_box: tuple[Vec3, Vec3],
    edges: tuple[tuple[int, int], ...],
) -> MeshPythonData:
    """Assemble the stable plain-Python mesh inspection dictionary."""
    return {
        "vertices": vertices,
        "faces": faces,
        "normals": normals,
        "texcoords": texcoords,
        "material": material,
        "bounding_box": bounding_box,
        "edges": edges,
    }
