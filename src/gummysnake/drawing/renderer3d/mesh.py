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


class Mesh3D:
    """Indexed mesh data in logical model coordinates.

    Canonical mesh data is stored by the required Rust canvas runtime. Immutable
    tuple buffers are materialized lazily only for Python inspection/interchange,
    so NumPy is not required for normal imports, primitive generation, projection,
    or export. NumPy array views remain available through the ``*_array()`` methods
    when the optional dependency is installed.
    """

    __slots__ = (
        "_face_indices",
        "_face_offsets",
        "_faces_cache",
        "_normals",
        "_normals_cache",
        "_texcoords",
        "_texcoords_cache",
        "_rust_handle",
        "_vertices",
        "_vertices_cache",
        "material",
    )

    def __init__(
        self,
        vertices: MeshFloatInput = (),
        faces: MeshFaceInput = (),
        normals: MeshFloatInput = (),
        texcoords: MeshFloatInput = (),
        material: Material3D | None = None,
        *,
        face_indices: MeshIndexInput | None = None,
        face_offsets: MeshIndexInput | None = None,
        rust_handle: MeshRustHandle | None = None,
    ) -> None:
        """Create a mesh from Python buffers or an existing Rust-owned handle.

        Args:
            vertices: Vertex positions as ``(x, y, z)`` rows, ``Vec3`` objects,
                or a NumPy-style two-dimensional array.
            faces: Face definitions as rows of vertex indices. Each row may have
                any length, which allows triangles, quads, and polygons.
            normals: Optional vertex normals as ``(x, y, z)`` rows. Leave empty
                when normals should be computed later or are not needed.
            texcoords: Optional texture coordinates as ``(u, v)`` rows.
            material: Optional material used when this mesh is drawn as part of a
                model.
            face_indices: Optional flat index buffer for callers that already
                store faces in packed form.
            face_offsets: Offsets into ``face_indices``. Provide this only when
                ``face_indices`` is also provided.
            rust_handle: Existing canvas-runtime mesh handle. This is used by
                loaders and primitive generators to avoid materializing Python
                buffers until inspection is requested.
        """
        self.material = material
        self._rust_handle: MeshRustHandle | None = rust_handle
        self._vertices_cache: tuple[Vec3, ...] | None = None
        self._faces_cache: tuple[tuple[int, ...], ...] | None = None
        self._normals_cache: tuple[Vec3, ...] | None = None
        self._texcoords_cache: tuple[tuple[float, float], ...] | None = None
        self._vertices: tuple[tuple[float, float, float], ...] | None = None
        self._face_indices: tuple[int, ...] | None = None
        self._face_offsets: tuple[int, ...] | None = None
        self._normals: tuple[tuple[float, float, float], ...] | None = None
        self._texcoords: tuple[tuple[float, float], ...] | None = None
        if rust_handle is not None:
            return

        vertices_array = coerce_vec3_rows(vertices, name="vertices")
        face_indices_tuple, face_offsets_tuple = resolve_face_buffers(
            faces, face_indices, face_offsets, len(vertices_array)
        )
        self._rust_handle = create_rust_mesh_handle(
            vertices_array,
            face_indices_tuple,
            face_offsets_tuple,
            coerce_vec3_rows(normals, name="normals"),
            coerce_vec2_rows(texcoords, name="texcoords"),
        )

    @classmethod
    def from_arrays(
        cls,
        vertices: MeshFloatInput,
        *,
        faces: MeshFaceInput = (),
        normals: MeshFloatInput = (),
        texcoords: MeshFloatInput = (),
        face_indices: MeshIndexInput | None = None,
        face_offsets: MeshIndexInput | None = None,
        material: Material3D | None = None,
    ) -> Mesh3D:
        """Build a mesh from Python sequences or NumPy-style arrays.

        Args:
            vertices: Vertex positions as ``(x, y, z)`` rows, ``Vec3`` objects,
                or a two-dimensional array-like object.
            faces: Face rows containing indices into ``vertices``.
            normals: Optional vertex-normal rows. Empty input means no normals
                are attached.
            texcoords: Optional texture-coordinate rows as ``(u, v)`` pairs.
            face_indices: Optional packed face index buffer. Use this with
                ``face_offsets`` when faces are already stored in flat form.
            face_offsets: Offsets into ``face_indices``. The first value must be
                ``0`` and the last must be ``len(face_indices)``.
            material: Optional material to associate with the mesh.

        Returns:
            A ``Mesh3D`` whose canonical storage lives in the Rust canvas runtime.
        """
        return cls(
            vertices,
            faces,
            normals,
            texcoords,
            material,
            face_indices=face_indices,
            face_offsets=face_offsets,
        )

    @classmethod
    def from_rust_handle(
        cls, rust_handle: MeshRustHandle, *, material: Material3D | None = None
    ) -> Mesh3D:
        """Wrap an existing Rust canvas mesh handle.

        Args:
            rust_handle: Mesh handle returned by the canvas runtime.
            material: Optional material to associate with the mesh wrapper.

        Returns:
            A ``Mesh3D`` wrapper that lazily reads data from ``rust_handle``.
        """
        return cls(material=material, rust_handle=rust_handle)

    def _ensure_arrays(self) -> None:
        if self._vertices is not None:
            return
        if self._rust_handle is None:
            raise RuntimeError("Mesh3D has no Rust canvas mesh handle.")
        payload = self._rust_handle.to_mesh_payload()
        vertices = coerce_vec3_rows(cast(MeshFloatInput, payload["vertices"]), name="vertices")
        indices, offsets = pack_faces(cast(MeshFaceInput, payload["faces"]), len(vertices))
        self._vertices = vertices
        self._face_indices = indices
        self._face_offsets = offsets
        self._normals = coerce_vec3_rows(
            cast(MeshFloatInput, payload.get("normals", ())), name="normals"
        )
        self._texcoords = coerce_vec2_rows(
            cast(MeshFloatInput, payload.get("texcoords", ())), name="texcoords"
        )

    @property
    def vertices(self) -> tuple[Vec3, ...]:
        """Vertex positions as immutable ``Vec3`` values.

        Returns:
            One ``Vec3`` for each vertex in the mesh.
        """
        self._ensure_arrays()
        assert self._vertices is not None
        if self._vertices_cache is None:
            self._vertices_cache = tuple(Vec3(x, y, z) for x, y, z in self._vertices)
        return self._vertices_cache

    @property
    def faces(self) -> tuple[tuple[int, ...], ...]:
        """Face definitions as immutable rows of vertex indices.

        Returns:
            A tuple of faces. Each face contains indices into ``vertices``.
        """
        self._ensure_arrays()
        assert self._face_indices is not None
        assert self._face_offsets is not None
        if self._faces_cache is None:
            faces = []
            for start, stop in zip(self._face_offsets[:-1], self._face_offsets[1:], strict=True):
                faces.append(tuple(self._face_indices[start:stop]))
            self._faces_cache = tuple(faces)
        return self._faces_cache

    @property
    def normals(self) -> tuple[Vec3, ...]:
        """Vertex normals as immutable ``Vec3`` values.

        Returns:
            One normal for each stored normal row. The tuple may be empty when the
            mesh has no normals.
        """
        self._ensure_arrays()
        assert self._normals is not None
        if self._normals_cache is None:
            self._normals_cache = tuple(Vec3(x, y, z) for x, y, z in self._normals)
        return self._normals_cache

    @property
    def texcoords(self) -> tuple[tuple[float, float], ...]:
        """Texture coordinates as immutable ``(u, v)`` pairs.

        Returns:
            Stored texture coordinates, or an empty tuple when the mesh has none.
        """
        self._ensure_arrays()
        assert self._texcoords is not None
        if self._texcoords_cache is None:
            self._texcoords_cache = self._texcoords
        return self._texcoords_cache

    def vertex_array(self, *, copy: bool = False) -> NumpyArray:
        """Return vertices as a NumPy array.

        Args:
            copy: When ``True``, return a writable copy. When ``False``, return a
                read-only array view/copy suitable for inspection.

        Returns:
            A NumPy array with shape ``(vertex_count, 3)``.
        """
        self._ensure_arrays()
        assert self._vertices is not None
        return _readonly_numpy_array(self._vertices, dtype="float64", copy=copy)

    def normal_array(self, *, copy: bool = False) -> NumpyArray:
        """Return vertex normals as a NumPy array.

        Args:
            copy: When ``True``, return a writable copy. When ``False``, return a
                read-only array view/copy suitable for inspection.

        Returns:
            A NumPy array with shape ``(normal_count, 3)``.
        """
        self._ensure_arrays()
        assert self._normals is not None
        return _readonly_numpy_array(self._normals, dtype="float64", copy=copy)

    def texcoord_array(self, *, copy: bool = False) -> NumpyArray:
        """Return texture coordinates as a NumPy array.

        Args:
            copy: When ``True``, return a writable copy. When ``False``, return a
                read-only array view/copy suitable for inspection.

        Returns:
            A NumPy array with shape ``(texcoord_count, 2)``.
        """
        self._ensure_arrays()
        assert self._texcoords is not None
        return _readonly_numpy_array(self._texcoords, dtype="float64", copy=copy)

    def face_index_array(self, *, copy: bool = False) -> NumpyArray:
        """Return the flat face index buffer as a NumPy array.

        Args:
            copy: When ``True``, return a writable copy. When ``False``, return a
                read-only array view/copy suitable for inspection.

        Returns:
            A one-dimensional integer array containing all face indices.
        """
        self._ensure_arrays()
        assert self._face_indices is not None
        return _readonly_numpy_array(self._face_indices, dtype="int64", copy=copy)

    def face_offset_array(self, *, copy: bool = False) -> NumpyArray:
        """Return face offsets as a NumPy array.

        Args:
            copy: When ``True``, return a writable copy. When ``False``, return a
                read-only array view/copy suitable for inspection.

        Returns:
            A one-dimensional integer array. Consecutive offset pairs slice the
            flat face index buffer for each face.
        """
        self._ensure_arrays()
        assert self._face_offsets is not None
        return _readonly_numpy_array(self._face_offsets, dtype="int64", copy=copy)

    @property
    def bounding_box(self) -> tuple[Vec3, Vec3]:
        """Axis-aligned bounds of the mesh.

        Returns:
            ``(minimum, maximum)`` corners as ``Vec3`` values. Empty meshes return
            the origin for both corners.
        """
        vertices = self.vertices
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

    def edges(self) -> tuple[tuple[int, int], ...]:
        """List unique mesh edges.

        Returns:
            Sorted ``(start_index, end_index)`` pairs. Each pair uses the smaller
            index first so shared face edges appear only once.
        """
        edges: set[tuple[int, int]] = set()
        for face in self.faces:
            if len(face) < 2:
                continue
            for start, end in zip(face, (*face[1:], face[0]), strict=True):
                edges.add((min(start, end), max(start, end)))
        return tuple(sorted(edges))

    def normalized(self, size: float = 1.0) -> Mesh3D:
        """Return a centered copy scaled to fit inside a cube.

        Args:
            size: Target length of the largest mesh dimension.

        Returns:
            A new ``Mesh3D`` with the same faces, normals, texture coordinates,
            and material, but with centered and scaled vertex positions.
        """
        min_corner, max_corner = self.bounding_box
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
        return Mesh3D(
            vertices=tuple(
                Vec3(
                    (vertex.x - center.x) * scale,
                    (vertex.y - center.y) * scale,
                    (vertex.z - center.z) * scale,
                )
                for vertex in self.vertices
            ),
            faces=self.faces,
            normals=self.normals,
            texcoords=self.texcoords,
            material=self.material,
        )

    def flip_u(self) -> Mesh3D:
        """Return a copy with horizontal texture coordinates mirrored.

        Returns:
            A new mesh where each texture ``u`` value is replaced by ``1 - u``.
        """
        return self.with_texcoords(tuple((1.0 - u, v) for u, v in self.texcoords))

    def flip_v(self) -> Mesh3D:
        """Return a copy with vertical texture coordinates mirrored.

        Returns:
            A new mesh where each texture ``v`` value is replaced by ``1 - v``.
        """
        return self.with_texcoords(tuple((u, 1.0 - v) for u, v in self.texcoords))

    def with_texcoords(self, texcoords: Sequence[Sequence[float]]) -> Mesh3D:
        """Return a copy with different texture coordinates.

        Args:
            texcoords: New ``(u, v)`` texture-coordinate rows.

        Returns:
            A new mesh with the same geometry, normals, and material.
        """
        return Mesh3D(
            vertices=self.vertices,
            faces=self.faces,
            normals=self.normals,
            texcoords=texcoords,
            material=self.material,
        )

    def compute_face_normals(self) -> tuple[Vec3, ...]:
        """Compute one normal vector for each face.

        Returns:
            Face normals in the same order as ``faces``. Degenerate faces use the
            default normal ``Vec3(0, 0, 1)``.
        """
        normals: list[Vec3] = []
        vertices = self.vertices
        for face in self.faces:
            if len(face) < 3:
                normals.append(Vec3(0.0, 0.0, 1.0))
                continue
            a, b, c = vertices[face[0]], vertices[face[1]], vertices[face[2]]
            normals.append(_normalize(_cross(_sub(b, a), _sub(c, a))))
        return tuple(normals)

    def with_computed_normals(self) -> Mesh3D:
        """Return a copy with averaged vertex normals.

        Returns:
            A new mesh whose normals are computed from the surrounding face
            normals for each vertex.
        """
        face_normals = self.compute_face_normals()
        vertex_normals = [Vec3(0.0, 0.0, 0.0) for _ in self.vertices]
        counts = [0 for _ in self.vertices]
        for face, normal in zip(self.faces, face_normals, strict=True):
            for index in face:
                vertex_normals[index] = Vec3(
                    vertex_normals[index].x + normal.x,
                    vertex_normals[index].y + normal.y,
                    vertex_normals[index].z + normal.z,
                )
                counts[index] += 1
        averaged = tuple(
            _normalize(
                Vec3(
                    n.x / max(1, counts[index]),
                    n.y / max(1, counts[index]),
                    n.z / max(1, counts[index]),
                )
            )
            for index, n in enumerate(vertex_normals)
        )
        return Mesh3D(
            vertices=self.vertices,
            faces=self.faces,
            normals=averaged,
            texcoords=self.texcoords,
            material=self.material,
        )

    def clear_colors(self) -> Mesh3D:
        """Return this mesh unchanged because ``Mesh3D`` does not store colors.

        Returns:
            The same mesh instance.
        """
        return self

    def to_python(self) -> MeshPythonData:
        """Return mesh data as plain Python containers.

        Returns:
            A dictionary containing vertices, faces, normals, texture
            coordinates, material, bounding box, and unique edges.
        """
        return {
            "vertices": self.vertices,
            "faces": self.faces,
            "normals": self.normals,
            "texcoords": self.texcoords,
            "material": self.material,
            "bounding_box": self.bounding_box,
            "edges": self.edges(),
        }

    def __repr__(self) -> str:
        self._ensure_arrays()
        assert self._vertices is not None
        assert self._face_offsets is not None
        assert self._normals is not None
        assert self._texcoords is not None
        return (
            f"Mesh3D(vertices={len(self._vertices)}, faces={len(self._face_offsets) - 1}, "
            f"normals={len(self._normals)}, texcoords={len(self._texcoords)}, "
            f"rust_owned={self._rust_handle is not None}, material={self.material!r})"
        )


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
