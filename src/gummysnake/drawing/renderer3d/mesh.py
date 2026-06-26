"""Mesh storage and conversion helpers for 3D rendering."""

from __future__ import annotations

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
        self._ensure_arrays()
        assert self._vertices is not None
        if self._vertices_cache is None:
            self._vertices_cache = tuple(Vec3(x, y, z) for x, y, z in self._vertices)
        return self._vertices_cache

    @property
    def faces(self) -> tuple[tuple[int, ...], ...]:
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
        self._ensure_arrays()
        assert self._normals is not None
        if self._normals_cache is None:
            self._normals_cache = tuple(Vec3(x, y, z) for x, y, z in self._normals)
        return self._normals_cache

    @property
    def texcoords(self) -> tuple[tuple[float, float], ...]:
        self._ensure_arrays()
        assert self._texcoords is not None
        if self._texcoords_cache is None:
            self._texcoords_cache = self._texcoords
        return self._texcoords_cache

    def vertex_array(self, *, copy: bool = False) -> Any:
        self._ensure_arrays()
        assert self._vertices is not None
        return _readonly_numpy_array(self._vertices, dtype="float64", copy=copy)

    def normal_array(self, *, copy: bool = False) -> Any:
        self._ensure_arrays()
        assert self._normals is not None
        return _readonly_numpy_array(self._normals, dtype="float64", copy=copy)

    def texcoord_array(self, *, copy: bool = False) -> Any:
        self._ensure_arrays()
        assert self._texcoords is not None
        return _readonly_numpy_array(self._texcoords, dtype="float64", copy=copy)

    def face_index_array(self, *, copy: bool = False) -> Any:
        self._ensure_arrays()
        assert self._face_indices is not None
        return _readonly_numpy_array(self._face_indices, dtype="int64", copy=copy)

    def face_offset_array(self, *, copy: bool = False) -> Any:
        self._ensure_arrays()
        assert self._face_offsets is not None
        return _readonly_numpy_array(self._face_offsets, dtype="int64", copy=copy)

    def to_python(self) -> dict[str, object]:
        return {
            "vertices": self.vertices,
            "faces": self.faces,
            "normals": self.normals,
            "texcoords": self.texcoords,
            "material": self.material,
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


def _mesh_rust_handle(mesh: Mesh3D) -> Any | None:
    return mesh._rust_handle
