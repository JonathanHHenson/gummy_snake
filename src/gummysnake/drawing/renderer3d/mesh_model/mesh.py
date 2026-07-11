"""Public ``Mesh3D`` wrapper over Rust-owned canonical mesh storage."""

from __future__ import annotations

from collections.abc import Sequence

from gummysnake.drawing.renderer3d._mesh_buffers import (
    MeshFaceInput,
    MeshFloatInput,
    MeshIndexInput,
    MeshRustHandle,
)
from gummysnake.drawing.renderer3d._numpy import NumpyArray
from gummysnake.drawing.renderer3d.materials import Material3D
from gummysnake.drawing.renderer3d.mesh_model.geometry import (
    averaged_vertex_normals,
    face_normals,
    flipped_texcoords,
    mesh_bounding_box,
    mesh_edges,
    normalized_vertices,
)
from gummysnake.drawing.renderer3d.mesh_model.python_data import (
    MeshPythonCache,
    MeshPythonData,
    ensure_mesh_buffers,
    face_index_array,
    face_offset_array,
    mesh_faces,
    mesh_normals,
    mesh_python_data,
    mesh_texcoords,
    mesh_vertices,
    normal_array,
    texcoord_array,
    vertex_array,
)
from gummysnake.drawing.renderer3d.mesh_model.storage import create_mesh_handle_from_input
from gummysnake.drawing.renderer3d.types import Vec3


class Mesh3D:
    """Indexed mesh data in logical model coordinates.

    Canonical mesh data is stored by the required Rust canvas runtime. Immutable
    tuple buffers are materialized lazily only for Python inspection/interchange,
    so NumPy is not required for normal imports, primitive generation, projection,
    or export. NumPy array views remain available through the ``*_array()`` methods
    when the optional dependency is installed.
    """

    __slots__ = ("_cache", "_rust_handle", "material")

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
        self._cache = MeshPythonCache()
        self._rust_handle = (
            rust_handle
            if rust_handle is not None
            else create_mesh_handle_from_input(
                vertices,
                faces,
                normals,
                texcoords,
                face_indices=face_indices,
                face_offsets=face_offsets,
            )
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
        """Hydrate immutable Python inspection buffers only when requested."""
        _ = ensure_mesh_buffers(self._cache, self._rust_handle)

    @property
    def vertices(self) -> tuple[Vec3, ...]:
        """Vertex positions as immutable ``Vec3`` values."""
        return mesh_vertices(self._cache, self._rust_handle)

    @property
    def faces(self) -> tuple[tuple[int, ...], ...]:
        """Face definitions as immutable rows of vertex indices."""
        return mesh_faces(self._cache, self._rust_handle)

    @property
    def normals(self) -> tuple[Vec3, ...]:
        """Vertex normals as immutable ``Vec3`` values."""
        return mesh_normals(self._cache, self._rust_handle)

    @property
    def texcoords(self) -> tuple[tuple[float, float], ...]:
        """Texture coordinates as immutable ``(u, v)`` pairs."""
        return mesh_texcoords(self._cache, self._rust_handle)

    def vertex_array(self, *, copy: bool = False) -> NumpyArray:
        """Return vertices as a NumPy array."""
        return vertex_array(self._cache, self._rust_handle, copy=copy)

    def normal_array(self, *, copy: bool = False) -> NumpyArray:
        """Return vertex normals as a NumPy array."""
        return normal_array(self._cache, self._rust_handle, copy=copy)

    def texcoord_array(self, *, copy: bool = False) -> NumpyArray:
        """Return texture coordinates as a NumPy array."""
        return texcoord_array(self._cache, self._rust_handle, copy=copy)

    def face_index_array(self, *, copy: bool = False) -> NumpyArray:
        """Return the flat face index buffer as a NumPy array."""
        return face_index_array(self._cache, self._rust_handle, copy=copy)

    def face_offset_array(self, *, copy: bool = False) -> NumpyArray:
        """Return face offsets as a NumPy array."""
        return face_offset_array(self._cache, self._rust_handle, copy=copy)

    @property
    def bounding_box(self) -> tuple[Vec3, Vec3]:
        """Axis-aligned bounds of the mesh in logical model coordinates."""
        return mesh_bounding_box(self.vertices)

    def edges(self) -> tuple[tuple[int, int], ...]:
        """List unique mesh edges with the smaller index first."""
        return mesh_edges(self.faces)

    def normalized(self, size: float = 1.0) -> Mesh3D:
        """Return a centered copy scaled to fit inside a cube."""
        return Mesh3D(
            vertices=normalized_vertices(self.vertices, size),
            faces=self.faces,
            normals=self.normals,
            texcoords=self.texcoords,
            material=self.material,
        )

    def flip_u(self) -> Mesh3D:
        """Return a copy with horizontal texture coordinates mirrored."""
        return self.with_texcoords(flipped_texcoords(self.texcoords, axis="u"))

    def flip_v(self) -> Mesh3D:
        """Return a copy with vertical texture coordinates mirrored."""
        return self.with_texcoords(flipped_texcoords(self.texcoords, axis="v"))

    def with_texcoords(self, texcoords: Sequence[Sequence[float]]) -> Mesh3D:
        """Return a copy with different texture coordinates."""
        return Mesh3D(
            vertices=self.vertices,
            faces=self.faces,
            normals=self.normals,
            texcoords=texcoords,
            material=self.material,
        )

    def compute_face_normals(self) -> tuple[Vec3, ...]:
        """Compute one normal vector for each face."""
        return face_normals(self.vertices, self.faces)

    def with_computed_normals(self) -> Mesh3D:
        """Return a copy with averaged vertex normals."""
        return Mesh3D(
            vertices=self.vertices,
            faces=self.faces,
            normals=averaged_vertex_normals(self.vertices, self.faces),
            texcoords=self.texcoords,
            material=self.material,
        )

    def clear_colors(self) -> Mesh3D:
        """Return this mesh unchanged because ``Mesh3D`` does not store colors."""
        return self

    def to_python(self) -> MeshPythonData:
        """Return mesh data as plain Python containers."""
        return mesh_python_data(
            vertices=self.vertices,
            faces=self.faces,
            normals=self.normals,
            texcoords=self.texcoords,
            material=self.material,
            bounding_box=self.bounding_box,
            edges=self.edges(),
        )

    def __repr__(self) -> str:
        buffers = ensure_mesh_buffers(self._cache, self._rust_handle)
        return (
            f"Mesh3D(vertices={len(buffers.vertices)}, faces={len(buffers.face_offsets) - 1}, "
            f"normals={len(buffers.normals)}, texcoords={len(buffers.texcoords)}, "
            f"rust_owned={self._rust_handle is not None}, material={self.material!r})"
        )
