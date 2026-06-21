"""Backend-agnostic 3D renderer protocol and value objects.

This module intentionally defines contracts only. Concrete 3D support lives in a
backend-specific renderer, while public APIs can depend on these Python-native data
structures without importing OpenGL, Pyglet, NumPy, or any other rendering package.
"""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from gummysnake.drawing.renderer import Renderer

type RGBA = tuple[float, float, float, float]
type Matrix4 = tuple[tuple[float, ...], ...]
type FloatRows = tuple[tuple[float, ...], ...]


class LightKind(StrEnum):
    """3D light source kinds."""

    AMBIENT = "ambient"
    DIRECTIONAL = "directional"
    POINT = "point"


@dataclass(frozen=True, slots=True)
class Vec3:
    """Simple immutable 3D vector used by renderer contracts and prototypes."""

    x: float
    y: float
    z: float

    def __array__(self, dtype: Any = None, copy: bool | None = None) -> Any:
        np = _require_numpy("Vec3.__array__()")
        array = np.array((self.x, self.y, self.z), dtype=np.float64)
        if dtype is not None:
            return array.astype(dtype, copy=False if copy is None else copy)
        if copy is False:
            return array
        return array.copy() if copy else array

    def to_array(self, *, copy: bool = True) -> Any:
        np = _require_numpy("Vec3.to_array()")
        array = np.array((self.x, self.y, self.z), dtype=np.float64)
        return array.copy() if copy else array

    @classmethod
    def from_array(cls, value: Any) -> Vec3:
        np = _require_numpy("Vec3.from_array()")
        array = np.asarray(value, dtype=np.float64)
        if array.shape != (3,):
            raise ValueError("Vec3 arrays must have shape (3,).")
        return cls(float(array[0]), float(array[1]), float(array[2]))


@dataclass(frozen=True, slots=True)
class Camera3D:
    """Camera orientation for future WEBGL-like renderers."""

    eye: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 500.0))
    target: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 0.0))
    up: Vec3 = field(default_factory=lambda: Vec3(0.0, 1.0, 0.0))


@dataclass(frozen=True, slots=True)
class PerspectiveProjection:
    """Perspective projection described in Gummy Snake-style degrees."""

    fov_y: float = 60.0
    aspect: float | None = None
    near: float = 0.1
    far: float = 10_000.0


@dataclass(frozen=True, slots=True)
class OrthographicProjection:
    """Orthographic projection dimensions in logical canvas units."""

    width: float
    height: float
    near: float = 0.1
    far: float = 10_000.0


type Projection3D = PerspectiveProjection | OrthographicProjection

type ShaderUniformValue = (
    bool | int | float | Vec3 | Texture3D | tuple[float, ...] | tuple[tuple[float, ...], ...]
)


@dataclass(frozen=True, slots=True)
class Light3D:
    """Light description independent of a concrete shader implementation."""

    kind: LightKind
    color: RGBA = (1.0, 1.0, 1.0, 1.0)
    intensity: float = 1.0
    position: Vec3 | None = None
    direction: Vec3 | None = None


@dataclass(frozen=True, slots=True)
class Texture3D:
    """Texture handle placeholder for future 3D renderers."""

    source: object
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class Material3D:
    """Material values shared by model, primitive, and shader workflows."""

    base_color: RGBA = (1.0, 1.0, 1.0, 1.0)
    emissive_color: RGBA = (0.0, 0.0, 0.0, 1.0)
    specular_color: RGBA = (1.0, 1.0, 1.0, 1.0)
    shininess: float = 32.0
    texture: Texture3D | None = None


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
            vertices_array, face_indices_tuple, face_offsets_tuple, normals_array, texcoords_array
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


def _require_numpy(feature: str) -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise ImportError(
            f"{feature} requires the optional numpy dependency. "
            "Install gummy-snake with the `numpy` extra."
        ) from exc
    return np


def _readonly_numpy_array(value: Any, *, dtype: str, copy: bool) -> Any:
    np = _require_numpy("Mesh3D ndarray export")
    array = np.ascontiguousarray(value, dtype=getattr(np, dtype))
    if not copy:
        array.setflags(write=False)
        return array
    return array.copy()


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


class Model3D:
    """Loaded or generated model made of one or more meshes.

    Models loaded by the canvas runtime keep a Rust-owned model handle for hot
    render/export paths. The public ``meshes`` view stays available and is
    materialized lazily when Python code inspects geometry.
    """

    __slots__ = ("_meshes", "_rust_handle", "source")

    def __init__(
        self,
        meshes: tuple[Mesh3D, ...] | None = None,
        source: Path | None = None,
        *,
        rust_handle: Any | None = None,
    ) -> None:
        self._meshes = meshes
        self._rust_handle = rust_handle
        self.source = source

    @property
    def meshes(self) -> tuple[Mesh3D, ...]:
        if self._meshes is None:
            self._meshes = self._materialize_rust_meshes()
        return self._meshes

    def _materialize_rust_meshes(self) -> tuple[Mesh3D, ...]:
        if self._rust_handle is None:
            return ()
        if hasattr(self._rust_handle, "to_mesh_handle"):
            return (Mesh3D.from_rust_handle(self._rust_handle.to_mesh_handle()),)
        payload = self._rust_handle.to_mesh_payload()
        vertices = tuple(Vec3(float(x), float(y), float(z)) for x, y, z in payload["vertices"])
        faces = tuple(tuple(int(index) for index in face) for face in payload["faces"])
        texcoords = tuple((float(u), float(v)) for u, v in payload.get("texcoords", ()))
        normals = tuple(
            Vec3(float(x), float(y), float(z)) for x, y, z in payload.get("normals", ())
        )
        return (Mesh3D(vertices=vertices, faces=faces, normals=normals, texcoords=texcoords),)


def _model_rust_handle(model: Model3D) -> Any | None:
    return model._rust_handle


def _mesh_rust_handle(mesh: Mesh3D) -> Any | None:
    return mesh._rust_handle


@dataclass(slots=True)
class Shader3D:
    """Python-native shader description for an OpenGL-style backend."""

    vertex_source: str
    fragment_source: str
    uniforms: MutableMapping[str, ShaderUniformValue] = field(default_factory=dict)
    vertex_path: Path | None = None
    fragment_path: Path | None = None

    def __post_init__(self) -> None:
        self.uniforms = dict(self.uniforms)

    def set_uniform(self, name: str, value: ShaderUniformValue) -> None:
        self.uniforms[name] = value

    def uniform(self, name: str, value: ShaderUniformValue) -> Shader3D:
        self.set_uniform(name, value)
        return self

    def version(self) -> str:
        if "#version 300 es" in self.vertex_source or "#version 300 es" in self.fragment_source:
            return "glsl-es-300"
        if "#version" in self.vertex_source or "#version" in self.fragment_source:
            return "glsl"
        return "glsl-es-100"

    def copy_to_context(self) -> Shader3D:
        return Shader3D(
            vertex_source=self.vertex_source,
            fragment_source=self.fragment_source,
            uniforms=dict(self.uniforms),
            vertex_path=self.vertex_path,
            fragment_path=self.fragment_path,
        )

    def inspect_hooks(self) -> dict[str, bool]:
        combined = f"{self.vertex_source}\n{self.fragment_source}"
        return {
            "vertex": "void main" in self.vertex_source,
            "fragment": "void main" in self.fragment_source,
            "uniforms": "uniform " in combined,
            "attributes": "attribute " in combined or "in " in self.vertex_source,
        }

    def modify(
        self,
        *,
        vertex_source: str | None = None,
        fragment_source: str | None = None,
        uniforms: MutableMapping[str, ShaderUniformValue] | None = None,
    ) -> Shader3D:
        next_uniforms = dict(self.uniforms)
        if uniforms is not None:
            next_uniforms.update(uniforms)
        return Shader3D(
            vertex_source=self.vertex_source if vertex_source is None else vertex_source,
            fragment_source=self.fragment_source if fragment_source is None else fragment_source,
            uniforms=next_uniforms,
            vertex_path=self.vertex_path,
            fragment_path=self.fragment_path,
        )


class Renderer3D(Renderer, Protocol):
    """Optional renderer protocol extension for WEBGL-like 3D support."""

    three_d: Literal[True]

    def set_camera(self, camera: Camera3D) -> None: ...

    def set_projection(self, projection: Projection3D) -> None: ...

    def set_lights(self, lights: Sequence[Light3D]) -> None: ...

    def set_material(self, material: Material3D | None) -> None: ...

    def set_texture(self, texture: Texture3D | None) -> None: ...

    def use_shader(self, shader: Shader3D | None) -> None: ...

    def set_shader_uniform(self, name: str, value: ShaderUniformValue) -> None: ...

    def draw_model(self, model: Model3D, transform: Matrix4 | None = None) -> None: ...

    def draw_mesh(self, mesh: Mesh3D, transform: Matrix4 | None = None) -> None: ...

    def plane(self, width: float, height: float) -> None: ...

    def box(self, width: float, height: float, depth: float) -> None: ...

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None: ...


__all__ = [
    "Camera3D",
    "Light3D",
    "LightKind",
    "Material3D",
    "Matrix4",
    "Mesh3D",
    "Model3D",
    "OrthographicProjection",
    "PerspectiveProjection",
    "Projection3D",
    "RGBA",
    "Renderer3D",
    "Shader3D",
    "ShaderUniformValue",
    "Texture3D",
    "Vec3",
    "_mesh_rust_handle",
    "_model_rust_handle",
]
