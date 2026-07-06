"""Private buffer conversion helpers for :class:`~gummysnake.drawing.renderer3d.Mesh3D`."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Protocol, SupportsIndex, SupportsInt, cast

from gummysnake.drawing.renderer3d.types import Vec3


class _ArrayLike(Protocol):
    @property
    def shape(self) -> Sequence[int]: ...


type MeshPayload = Mapping[str, object]


class MeshRustHandle(Protocol):
    """Rust-owned mesh handle exposed by the canvas runtime."""

    def to_mesh_payload(self) -> MeshPayload:
        """Materialize mesh data for Python inspection."""
        ...


type FloatRows = tuple[tuple[float, ...], ...]
type Vec3Rows = tuple[tuple[float, float, float], ...]
type Vec2Rows = tuple[tuple[float, float], ...]
type FaceBuffers = tuple[tuple[int, ...], tuple[int, ...]]
type MeshFloatInput = Iterable[Vec3 | Iterable[float]] | _ArrayLike
type MeshFaceInput = Iterable[Iterable[int]] | _ArrayLike
type MeshIndexInput = Iterable[int] | _ArrayLike
type _IntLike = str | bytes | bytearray | SupportsIndex | SupportsInt
type _MeshFactory = Callable[
    [
        list[tuple[float, ...]],
        list[tuple[int, ...]],
        list[tuple[float, ...]],
        list[tuple[float, ...]],
    ],
    MeshRustHandle,
]


def coerce_float_rows(value: MeshFloatInput, *, columns: int, name: str) -> FloatRows:
    """Coerce Python or array-like rows into immutable float tuples."""
    rows = _rows_from_array_like(value)
    if rows is None:
        rows = tuple(cast(Iterable[object], value))
    if not rows:
        return ()
    return tuple(_row_to_tuple(row, columns=columns, name=name) for row in rows)


def coerce_vec3_rows(value: MeshFloatInput, *, name: str) -> Vec3Rows:
    """Coerce 3D rows into immutable ``(x, y, z)`` tuples."""
    rows = coerce_float_rows(value, columns=3, name=name)
    return tuple((row[0], row[1], row[2]) for row in rows)


def coerce_vec2_rows(value: MeshFloatInput, *, name: str) -> Vec2Rows:
    """Coerce 2D rows into immutable ``(u, v)`` tuples."""
    rows = coerce_float_rows(value, columns=2, name=name)
    return tuple((row[0], row[1]) for row in rows)


def coerce_int_tuple(value: MeshIndexInput) -> tuple[int, ...]:
    """Coerce a Python or array-like integer buffer into an immutable tuple."""
    raw = _tolist_or_self(value)
    return tuple(int(item) for item in cast(Iterable[_IntLike], raw))


def resolve_face_buffers(
    faces: MeshFaceInput,
    face_indices: MeshIndexInput | None,
    face_offsets: MeshIndexInput | None,
    vertex_count: int,
) -> FaceBuffers:
    """Return validated flat face buffers from either flat buffers or face rows."""
    if face_indices is not None or face_offsets is not None:
        if face_indices is None or face_offsets is None:
            raise ValueError("face_indices and face_offsets must be provided together.")
        face_indices_tuple = coerce_int_tuple(face_indices)
        face_offsets_tuple = coerce_int_tuple(face_offsets)
        validate_face_buffers(face_indices_tuple, face_offsets_tuple, vertex_count)
        return face_indices_tuple, face_offsets_tuple
    return pack_faces(faces, vertex_count)


def pack_faces(faces: MeshFaceInput, vertex_count: int) -> FaceBuffers:
    """Pack variable-width face rows into flat index and offset buffers."""
    face_rows = cast(Iterable[Iterable[_IntLike]], _tolist_or_self(faces))
    indices: list[int] = []
    offsets = [0]
    for face in face_rows:
        packed = tuple(int(index) for index in face)
        if any(index < 0 or index >= vertex_count for index in packed):
            raise ValueError("Mesh3D face indices must reference existing vertices.")
        indices.extend(packed)
        offsets.append(len(indices))
    return tuple(indices), tuple(offsets)


def faces_from_buffers(indices: Sequence[int], offsets: Sequence[int]) -> list[tuple[int, ...]]:
    """Expand flat face buffers back into variable-width face rows."""
    return [
        tuple(int(index) for index in indices[start:stop])
        for start, stop in zip(offsets[:-1], offsets[1:], strict=True)
    ]


def create_rust_mesh_handle(
    vertices: Sequence[Sequence[float]],
    face_indices: Sequence[int],
    face_offsets: Sequence[int],
    normals: Sequence[Sequence[float]],
    texcoords: Sequence[Sequence[float]],
) -> MeshRustHandle:
    """Create the canonical Rust canvas mesh handle from Python buffers."""
    from gummysnake.rust.canvas import require_canvas_runtime

    runtime = require_canvas_runtime()
    factory = getattr(runtime, "create_mesh3d_handle", None)
    if not callable(factory):
        raise RuntimeError(
            "The installed canvas runtime does not provide create_mesh3d_handle(). "
            "Rebuild gummy_canvas."
        )
    mesh_factory = cast(_MeshFactory, factory)
    return mesh_factory(
        [tuple(float(value) for value in row) for row in vertices],
        faces_from_buffers(face_indices, face_offsets),
        [tuple(float(value) for value in row) for row in normals],
        [tuple(float(value) for value in row) for row in texcoords],
    )


def validate_face_buffers(
    indices: Sequence[int], offsets: Sequence[int], vertex_count: int
) -> None:
    """Validate flat face buffers before handing them to the Rust runtime."""
    if len(offsets) == 0 or offsets[0] != 0 or offsets[-1] != len(indices):
        raise ValueError("Mesh3D face offsets must start at 0 and end at len(face_indices).")
    if any(stop < start for start, stop in zip(offsets[:-1], offsets[1:], strict=True)):
        raise ValueError("Mesh3D face offsets must be sorted.")
    if any(index < 0 or index >= vertex_count for index in indices):
        raise ValueError("Mesh3D face indices must reference existing vertices.")


def _rows_from_array_like(
    value: MeshFloatInput | MeshFaceInput | MeshIndexInput,
) -> tuple[object, ...] | None:
    shape_value = getattr(value, "shape", None)
    if shape_value is None:
        return None
    shape = tuple(int(dimension) for dimension in cast(Iterable[_IntLike], shape_value))
    if len(shape) == 1:
        return tuple(cast(Iterable[object], _tolist_or_self(value)))
    if len(shape) == 2:
        rows = _tolist_or_self(value)
        return tuple(cast(Iterable[object], rows))
    raise ValueError("Array-like mesh inputs must be one- or two-dimensional.")


def _row_to_tuple(row: object, *, columns: int, name: str) -> tuple[float, ...]:
    if columns == 3 and isinstance(row, Vec3):
        return (float(row.x), float(row.y), float(row.z))
    if not isinstance(row, Iterable):
        raise ValueError(f"Mesh3D {name} rows must be iterable.")
    values = tuple(float(component) for component in row)
    if len(values) != columns:
        raise ValueError(f"Mesh3D {name} rows must have {columns} values.")
    return values


def _tolist_or_self(value: object) -> object:
    tolist = getattr(value, "tolist", None)
    return tolist() if callable(tolist) else value
