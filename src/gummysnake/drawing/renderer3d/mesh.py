"""Mesh storage and conversion helpers for 3D rendering."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any, cast

from gummysnake.drawing.renderer3d._numpy import _readonly_numpy_array
from gummysnake.drawing.renderer3d.materials import Material3D
from gummysnake.drawing.renderer3d.types import Vec3

type FloatRows = tuple[tuple[float, ...], ...]


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
        vertices: Sequence[Vec3 | Sequence[float]] | Any = (),
        faces: Sequence[Sequence[int]] | Any = (),
        normals: Sequence[Vec3 | Sequence[float]] | Any = (),
        texcoords: Sequence[Sequence[float]] | Any = (),
        material: Material3D | None = None,
        *,
        face_indices: Sequence[int] | Any | None = None,
        face_offsets: Sequence[int] | Any | None = None,
        rust_handle: Any | None = None,
    ) -> None:
        self.material = material
        self._rust_handle = rust_handle
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

        vertices_rows = _coerce_float_rows(vertices, columns=3, name="vertices")
        vertices_array: tuple[tuple[float, float, float], ...] = tuple(
            (row[0], row[1], row[2]) for row in vertices_rows
        )
        if face_indices is not None or face_offsets is not None:
            if face_indices is None or face_offsets is None:
                raise ValueError("face_indices and face_offsets must be provided together.")
            face_indices_tuple = _coerce_int_tuple(face_indices)
            face_offsets_tuple = _coerce_int_tuple(face_offsets)
            _validate_face_buffers(face_indices_tuple, face_offsets_tuple, len(vertices_array))
        else:
            face_indices_tuple, face_offsets_tuple = _pack_faces(faces, len(vertices_array))
        normal_rows = _coerce_float_rows(normals, columns=3, name="normals")
        texcoord_rows = _coerce_float_rows(texcoords, columns=2, name="texcoords")
        normals_array: tuple[tuple[float, float, float], ...] = tuple(
            (row[0], row[1], row[2]) for row in normal_rows
        )
        texcoords_array: tuple[tuple[float, float], ...] = tuple(
            (row[0], row[1]) for row in texcoord_rows
        )
        self._rust_handle = _create_rust_mesh_handle(
            vertices_array,
            face_indices_tuple,
            face_offsets_tuple,
            normals_array,
            texcoords_array,
        )

    @classmethod
    def from_arrays(
        cls,
        vertices: Any,
        *,
        faces: Sequence[Sequence[int]] | Any = (),
        normals: Any = (),
        texcoords: Any = (),
        face_indices: Any | None = None,
        face_offsets: Any | None = None,
        material: Material3D | None = None,
    ) -> Mesh3D:
        """From arrays.
        
        Args:
            vertices: The vertices value. Expected type: `Any`.
            faces: The faces value. Expected type: `Sequence[Sequence[int]] | Any`. Defaults to
                `()`.
            normals: The normals value. Expected type: `Any`. Defaults to `()`.
            texcoords: The texcoords value. Expected type: `Any`. Defaults to `()`.
            face_indices: The face indices value. Expected type: `Any | None`. Defaults to `None`.
            face_offsets: The face offsets value. Expected type: `Any | None`. Defaults to `None`.
            material: The material value. Expected type: `Material3D | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Mesh3D`.
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
    def from_rust_handle(cls, rust_handle: Any, *, material: Material3D | None = None) -> Mesh3D:
        """From rust handle.
        
        Args:
            rust_handle: The rust handle value. Expected type: `Any`.
            material: The material value. Expected type: `Material3D | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `Mesh3D`.
        """
        return cls(material=material, rust_handle=rust_handle)

    def _ensure_arrays(self) -> None:
        if self._vertices is not None:
            return
        if self._rust_handle is None:
            raise RuntimeError("Mesh3D has no Rust canvas mesh handle.")
        payload = self._rust_handle.to_mesh_payload()
        vertices_rows = _coerce_float_rows(payload["vertices"], columns=3, name="vertices")
        vertices: tuple[tuple[float, float, float], ...] = tuple(
            (row[0], row[1], row[2]) for row in vertices_rows
        )
        indices, offsets = _pack_faces(payload["faces"], len(vertices))
        normal_rows = _coerce_float_rows(payload.get("normals", ()), columns=3, name="normals")
        texcoord_rows = _coerce_float_rows(
            payload.get("texcoords", ()), columns=2, name="texcoords"
        )
        self._vertices = vertices
        self._face_indices = indices
        self._face_offsets = offsets
        self._normals = tuple((row[0], row[1], row[2]) for row in normal_rows)
        self._texcoords = tuple((row[0], row[1]) for row in texcoord_rows)

    @property
    def vertices(self) -> tuple[Vec3, ...]:
        """Vertices.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[Vec3, ...]`.
        """
        self._ensure_arrays()
        assert self._vertices is not None
        if self._vertices_cache is None:
            self._vertices_cache = tuple(Vec3(x, y, z) for x, y, z in self._vertices)
        return self._vertices_cache

    @property
    def faces(self) -> tuple[tuple[int, ...], ...]:
        """Faces.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[tuple[int, ...], ...]`.
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
        """Normals.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[Vec3, ...]`.
        """
        self._ensure_arrays()
        assert self._normals is not None
        if self._normals_cache is None:
            self._normals_cache = tuple(Vec3(x, y, z) for x, y, z in self._normals)
        return self._normals_cache

    @property
    def texcoords(self) -> tuple[tuple[float, float], ...]:
        """Texcoords.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[tuple[float, float], ...]`.
        """
        self._ensure_arrays()
        assert self._texcoords is not None
        if self._texcoords_cache is None:
            self._texcoords_cache = self._texcoords
        return self._texcoords_cache

    def vertex_array(self, *, copy: bool = False) -> Any:
        """Vertex array.
        
        Args:
            copy: The copy value. Expected type: `bool`. Defaults to `False`.
        
        Returns:
            The return value. Type: `Any`.
        """
        self._ensure_arrays()
        assert self._vertices is not None
        return _readonly_numpy_array(self._vertices, dtype="float64", copy=copy)

    def normal_array(self, *, copy: bool = False) -> Any:
        """Normal array.
        
        Args:
            copy: The copy value. Expected type: `bool`. Defaults to `False`.
        
        Returns:
            The return value. Type: `Any`.
        """
        self._ensure_arrays()
        assert self._normals is not None
        return _readonly_numpy_array(self._normals, dtype="float64", copy=copy)

    def texcoord_array(self, *, copy: bool = False) -> Any:
        """Texcoord array.
        
        Args:
            copy: The copy value. Expected type: `bool`. Defaults to `False`.
        
        Returns:
            The return value. Type: `Any`.
        """
        self._ensure_arrays()
        assert self._texcoords is not None
        return _readonly_numpy_array(self._texcoords, dtype="float64", copy=copy)

    def face_index_array(self, *, copy: bool = False) -> Any:
        """Face index array.
        
        Args:
            copy: The copy value. Expected type: `bool`. Defaults to `False`.
        
        Returns:
            The return value. Type: `Any`.
        """
        self._ensure_arrays()
        assert self._face_indices is not None
        return _readonly_numpy_array(self._face_indices, dtype="int64", copy=copy)

    def face_offset_array(self, *, copy: bool = False) -> Any:
        """Face offset array.
        
        Args:
            copy: The copy value. Expected type: `bool`. Defaults to `False`.
        
        Returns:
            The return value. Type: `Any`.
        """
        self._ensure_arrays()
        assert self._face_offsets is not None
        return _readonly_numpy_array(self._face_offsets, dtype="int64", copy=copy)

    @property
    def bounding_box(self) -> tuple[Vec3, Vec3]:
        """Bounding box.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[Vec3, Vec3]`.
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
        """Edges.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[tuple[int, int], ...]`.
        """
        edges: set[tuple[int, int]] = set()
        for face in self.faces:
            if len(face) < 2:
                continue
            for start, end in zip(face, (*face[1:], face[0]), strict=True):
                edges.add((min(start, end), max(start, end)))
        return tuple(sorted(edges))

    def normalized(self, size: float = 1.0) -> Mesh3D:
        """Normalized.
        
        Args:
            size: The size value. Expected type: `float`. Defaults to `1.0`.
        
        Returns:
            The return value. Type: `Mesh3D`.
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
        """Flip u.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Mesh3D`.
        """
        return self.with_texcoords(tuple((1.0 - u, v) for u, v in self.texcoords))

    def flip_v(self) -> Mesh3D:
        """Flip v.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Mesh3D`.
        """
        return self.with_texcoords(tuple((u, 1.0 - v) for u, v in self.texcoords))

    def with_texcoords(self, texcoords: Sequence[Sequence[float]]) -> Mesh3D:
        """With texcoords.
        
        Args:
            texcoords: The texcoords value. Expected type: `Sequence[Sequence[float]]`.
        
        Returns:
            The return value. Type: `Mesh3D`.
        """
        return Mesh3D(
            vertices=self.vertices,
            faces=self.faces,
            normals=self.normals,
            texcoords=texcoords,
            material=self.material,
        )

    def compute_face_normals(self) -> tuple[Vec3, ...]:
        """Compute face normals.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `tuple[Vec3, ...]`.
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
        """With computed normals.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Mesh3D`.
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
        """Clear colors.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Mesh3D`.
        """
        return self

    def to_python(self) -> dict[str, object]:
        """To python.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `dict[str, object]`.
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
        """Repr.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `str`.
        """
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


def _coerce_float_rows(value: Any, *, columns: int, name: str) -> FloatRows:
    rows = _rows_from_array_like(value)
    if rows is None:
        rows = tuple(value)
    if not rows:
        return ()
    return tuple(_row_to_tuple(row, columns=columns, name=name) for row in rows)


def _rows_from_array_like(value: Any) -> tuple[Any, ...] | None:
    shape = getattr(value, "shape", None)
    if shape is None:
        return None
    if len(shape) == 1:
        return tuple(value.tolist() if hasattr(value, "tolist") else value)
    if len(shape) == 2:
        rows = value.tolist() if hasattr(value, "tolist") else value
        return tuple(rows)
    raise ValueError("Array-like mesh inputs must be one- or two-dimensional.")


def _row_to_tuple(row: Any, *, columns: int, name: str) -> tuple[float, ...]:
    if columns == 3 and isinstance(row, Vec3):
        return (float(row.x), float(row.y), float(row.z))
    try:
        values = tuple(float(component) for component in row)
    except TypeError as exc:
        raise ValueError(f"Mesh3D {name} rows must be iterable.") from exc
    if len(values) != columns:
        raise ValueError(f"Mesh3D {name} rows must have {columns} values.")
    return values


def _coerce_int_tuple(value: Any) -> tuple[int, ...]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return tuple(int(item) for item in value)


def _pack_faces(
    faces: Sequence[Sequence[int]] | Any, vertex_count: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    tolist = getattr(faces, "tolist", None)
    face_rows = cast(Iterable[Any], tolist() if callable(tolist) else faces)
    indices: list[int] = []
    offsets = [0]
    for face in face_rows:
        packed = tuple(int(index) for index in face)
        if any(index < 0 or index >= vertex_count for index in packed):
            raise ValueError("Mesh3D face indices must reference existing vertices.")
        indices.extend(packed)
        offsets.append(len(indices))
    return tuple(indices), tuple(offsets)


def _faces_from_buffers(indices: Sequence[int], offsets: Sequence[int]) -> list[tuple[int, ...]]:
    return [
        tuple(int(index) for index in indices[start:stop])
        for start, stop in zip(offsets[:-1], offsets[1:], strict=True)
    ]


def _create_rust_mesh_handle(
    vertices: Sequence[Sequence[float]],
    face_indices: Sequence[int],
    face_offsets: Sequence[int],
    normals: Sequence[Sequence[float]],
    texcoords: Sequence[Sequence[float]],
) -> Any:
    from gummysnake.rust.canvas import require_canvas_runtime

    runtime = require_canvas_runtime()
    factory = getattr(runtime, "create_mesh3d_handle", None)
    if not callable(factory):
        raise RuntimeError(
            "The installed canvas runtime does not provide create_mesh3d_handle(). "
            "Rebuild gummy_canvas."
        )
    return factory(
        [tuple(float(value) for value in row) for row in vertices],
        _faces_from_buffers(face_indices, face_offsets),
        [tuple(float(value) for value in row) for row in normals],
        [tuple(float(value) for value in row) for row in texcoords],
    )


def _validate_face_buffers(
    indices: Sequence[int], offsets: Sequence[int], vertex_count: int
) -> None:
    if len(offsets) == 0 or offsets[0] != 0 or offsets[-1] != len(indices):
        raise ValueError("Mesh3D face offsets must start at 0 and end at len(face_indices).")
    if any(stop < start for start, stop in zip(offsets[:-1], offsets[1:], strict=True)):
        raise ValueError("Mesh3D face offsets must be sorted.")
    if any(index < 0 or index >= vertex_count for index in indices):
        raise ValueError("Mesh3D face indices must reference existing vertices.")


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


def _mesh_rust_handle(mesh: Mesh3D) -> Any | None:
    return mesh._rust_handle
