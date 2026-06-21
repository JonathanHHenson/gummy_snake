"""Backend-agnostic 3D renderer protocol and value objects.

This module intentionally defines contracts only. Concrete 3D support will live in a
backend-specific renderer, while public APIs can depend on these Python-native data
structures without importing OpenGL, Pyglet, or any other rendering package.
"""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np

from gummysnake.drawing.renderer import Renderer

type RGBA = tuple[float, float, float, float]
type Matrix4 = tuple[tuple[float, ...], ...]


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

    def __array__(self, dtype: Any = None, copy: bool | None = None) -> np.ndarray:
        array = np.array((self.x, self.y, self.z), dtype=np.float64)
        if dtype is not None:
            return array.astype(dtype, copy=False if copy is None else copy)
        if copy is False:
            return array
        return array.copy() if copy else array

    def to_array(self, *, copy: bool = True) -> np.ndarray:
        array = np.array((self.x, self.y, self.z), dtype=np.float64)
        return array.copy() if copy else array

    @classmethod
    def from_array(cls, value: Any) -> Vec3:
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

    Numeric mesh buffers are stored as immutable NumPy arrays. Friendly tuple
    views remain available for sketch/user code and existing API compatibility.
    Faces are stored as compact offset/index arrays so mixed triangle/quad meshes
    do not require object-dtype NumPy arrays.
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
        vertices: Sequence[Vec3 | Sequence[float]] | np.ndarray = (),
        faces: Sequence[Sequence[int]] | np.ndarray = (),
        normals: Sequence[Vec3 | Sequence[float]] | np.ndarray = (),
        texcoords: Sequence[Sequence[float]] | np.ndarray = (),
        material: Material3D | None = None,
        *,
        face_indices: Sequence[int] | np.ndarray | None = None,
        face_offsets: Sequence[int] | np.ndarray | None = None,
        rust_handle: Any | None = None,
    ) -> None:
        self.material = material
        self._rust_handle = rust_handle
        self._vertices_cache: tuple[Vec3, ...] | None = None
        self._faces_cache: tuple[tuple[int, ...], ...] | None = None
        self._normals_cache: tuple[Vec3, ...] | None = None
        self._texcoords_cache: tuple[tuple[float, float], ...] | None = None
        self._vertices: np.ndarray | None = None
        self._face_indices: np.ndarray | None = None
        self._face_offsets: np.ndarray | None = None
        self._normals: np.ndarray | None = None
        self._texcoords: np.ndarray | None = None
        if rust_handle is not None:
            return

        vertices_array = _readonly_array(_coerce_float_array(vertices, columns=3, name="vertices"))
        if face_indices is not None or face_offsets is not None:
            if face_indices is None or face_offsets is None:
                raise ValueError("face_indices and face_offsets must be provided together.")
            indices = np.asarray(face_indices, dtype=np.int64)
            offsets = np.asarray(face_offsets, dtype=np.int64)
            _validate_face_buffers(indices, offsets, len(vertices_array))
            face_indices_array = _readonly_array(indices)
            face_offsets_array = _readonly_array(offsets)
        else:
            indices, offsets = _pack_faces(faces, len(vertices_array))
            face_indices_array = _readonly_array(indices)
            face_offsets_array = _readonly_array(offsets)
        normals_array = _readonly_array(_coerce_float_array(normals, columns=3, name="normals"))
        texcoords_array = _readonly_array(
            _coerce_float_array(texcoords, columns=2, name="texcoords")
        )
        rust_mesh_handle = _create_rust_mesh_handle(
            vertices_array, face_indices_array, face_offsets_array, normals_array, texcoords_array
        )
        if rust_mesh_handle is not None:
            self._rust_handle = rust_mesh_handle
            return
        self._vertices = vertices_array
        self._face_indices = face_indices_array
        self._face_offsets = face_offsets_array
        self._normals = normals_array
        self._texcoords = texcoords_array

    @classmethod
    def from_arrays(
        cls,
        vertices: Any,
        *,
        faces: Sequence[Sequence[int]] | np.ndarray = (),
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
            self._vertices = _readonly_array(np.empty((0, 3), dtype=np.float64))
            self._face_indices = _readonly_array(np.empty((0,), dtype=np.int64))
            self._face_offsets = _readonly_array(np.array([0], dtype=np.int64))
            self._normals = _readonly_array(np.empty((0, 3), dtype=np.float64))
            self._texcoords = _readonly_array(np.empty((0, 2), dtype=np.float64))
            return
        payload = self._rust_handle.to_mesh_payload()
        vertices = _readonly_array(
            _coerce_float_array(payload["vertices"], columns=3, name="vertices")
        )
        indices, offsets = _pack_faces(payload["faces"], len(vertices))
        self._vertices = vertices
        self._face_indices = _readonly_array(indices)
        self._face_offsets = _readonly_array(offsets)
        self._normals = _readonly_array(
            _coerce_float_array(payload.get("normals", ()), columns=3, name="normals")
        )
        self._texcoords = _readonly_array(
            _coerce_float_array(payload.get("texcoords", ()), columns=2, name="texcoords")
        )

    @property
    def vertices(self) -> tuple[Vec3, ...]:
        self._ensure_arrays()
        assert self._vertices is not None
        if self._vertices_cache is None:
            self._vertices_cache = tuple(
                Vec3(float(x), float(y), float(z)) for x, y, z in self._vertices
            )
        return self._vertices_cache

    @property
    def faces(self) -> tuple[tuple[int, ...], ...]:
        self._ensure_arrays()
        assert self._face_indices is not None
        assert self._face_offsets is not None
        if self._faces_cache is None:
            faces = []
            for start, stop in zip(self._face_offsets[:-1], self._face_offsets[1:], strict=True):
                faces.append(tuple(int(index) for index in self._face_indices[start:stop]))
            self._faces_cache = tuple(faces)
        return self._faces_cache

    @property
    def normals(self) -> tuple[Vec3, ...]:
        self._ensure_arrays()
        assert self._normals is not None
        if self._normals_cache is None:
            self._normals_cache = tuple(
                Vec3(float(x), float(y), float(z)) for x, y, z in self._normals
            )
        return self._normals_cache

    @property
    def texcoords(self) -> tuple[tuple[float, float], ...]:
        self._ensure_arrays()
        assert self._texcoords is not None
        if self._texcoords_cache is None:
            self._texcoords_cache = tuple((float(u), float(v)) for u, v in self._texcoords)
        return self._texcoords_cache

    def vertex_array(self, *, copy: bool = False) -> np.ndarray:
        self._ensure_arrays()
        assert self._vertices is not None
        return self._vertices.copy() if copy else self._vertices

    def normal_array(self, *, copy: bool = False) -> np.ndarray:
        self._ensure_arrays()
        assert self._normals is not None
        return self._normals.copy() if copy else self._normals

    def texcoord_array(self, *, copy: bool = False) -> np.ndarray:
        self._ensure_arrays()
        assert self._texcoords is not None
        return self._texcoords.copy() if copy else self._texcoords

    def face_index_array(self, *, copy: bool = False) -> np.ndarray:
        self._ensure_arrays()
        assert self._face_indices is not None
        return self._face_indices.copy() if copy else self._face_indices

    def face_offset_array(self, *, copy: bool = False) -> np.ndarray:
        self._ensure_arrays()
        assert self._face_offsets is not None
        return self._face_offsets.copy() if copy else self._face_offsets

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


def _readonly_array(array: np.ndarray) -> np.ndarray:
    readonly = np.ascontiguousarray(array)
    readonly.setflags(write=False)
    return readonly


def _coerce_float_array(value: Any, *, columns: int, name: str) -> np.ndarray:
    if isinstance(value, np.ndarray):
        array = np.asarray(value, dtype=np.float64)
    else:
        rows = list(value)
        if not rows:
            return np.empty((0, columns), dtype=np.float64)
        array = np.asarray(
            [_row_to_tuple(row, columns=columns, name=name) for row in rows], dtype=np.float64
        )
    if array.size == 0:
        return np.empty((0, columns), dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != columns:
        raise ValueError(f"Mesh3D {name} arrays must have shape (n, {columns}).")
    return array


def _row_to_tuple(row: Any, *, columns: int, name: str) -> tuple[float, ...]:
    if columns == 3 and isinstance(row, Vec3):
        return (row.x, row.y, row.z)
    try:
        values = tuple(float(component) for component in row)
    except TypeError as exc:
        raise ValueError(f"Mesh3D {name} rows must be iterable.") from exc
    if len(values) != columns:
        raise ValueError(f"Mesh3D {name} rows must have {columns} values.")
    return values


def _pack_faces(
    faces: Sequence[Sequence[int]] | np.ndarray, vertex_count: int
) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(faces, np.ndarray) and faces.ndim == 2:
        face_rows: Iterable[Any] = faces.tolist()
    else:
        face_rows = faces
    indices: list[int] = []
    offsets = [0]
    for face in face_rows:
        packed = tuple(int(index) for index in face)
        if any(index < 0 or index >= vertex_count for index in packed):
            raise ValueError("Mesh3D face indices must reference existing vertices.")
        indices.extend(packed)
        offsets.append(len(indices))
    return np.asarray(indices, dtype=np.int64), np.asarray(offsets, dtype=np.int64)


def _faces_from_buffers(indices: np.ndarray, offsets: np.ndarray) -> list[tuple[int, ...]]:
    return [
        tuple(int(index) for index in indices[start:stop])
        for start, stop in zip(offsets[:-1], offsets[1:], strict=True)
    ]


def _create_rust_mesh_handle(
    vertices: np.ndarray,
    face_indices: np.ndarray,
    face_offsets: np.ndarray,
    normals: np.ndarray,
    texcoords: np.ndarray,
) -> Any | None:
    try:
        from gummysnake.rust.canvas import is_canvas_runtime_available, require_canvas_runtime
    except Exception:
        return None
    if not is_canvas_runtime_available():
        return None
    runtime = require_canvas_runtime()
    factory = getattr(runtime, "create_mesh3d_handle", None)
    if factory is None:
        return None
    return factory(
        [tuple(float(value) for value in row) for row in vertices],
        _faces_from_buffers(face_indices, face_offsets),
        [tuple(float(value) for value in row) for row in normals],
        [tuple(float(value) for value in row) for row in texcoords],
    )


def _validate_face_buffers(indices: np.ndarray, offsets: np.ndarray, vertex_count: int) -> None:
    if indices.ndim != 1 or offsets.ndim != 1:
        raise ValueError("Mesh3D face index and offset arrays must be one-dimensional.")
    if len(offsets) == 0 or offsets[0] != 0 or offsets[-1] != len(indices):
        raise ValueError("Mesh3D face offsets must start at 0 and end at len(face_indices).")
    if np.any(offsets[1:] < offsets[:-1]):
        raise ValueError("Mesh3D face offsets must be sorted.")
    if len(indices) and (np.any(indices < 0) or np.any(indices >= vertex_count)):
        raise ValueError("Mesh3D face indices must reference existing vertices.")


class Model3D:
    """Loaded or generated model made of one or more meshes.

    Models loaded by the canvas runtime may keep a Rust-owned model handle for hot
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
