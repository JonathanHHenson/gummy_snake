"""Backend-agnostic 3D renderer protocol and value objects.

This module intentionally defines contracts only. Concrete 3D support will live in a
backend-specific renderer, while public APIs can depend on these Python-native data
structures without importing OpenGL, Pyglet, or any other rendering package.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from p5_py.drawing.renderer import Renderer

type RGBA = tuple[float, float, float, float]
type Matrix4 = tuple[tuple[float, ...], ...]
type LightKind = Literal["ambient", "directional", "point"]


@dataclass(frozen=True, slots=True)
class Vec3:
    """Simple immutable 3D vector used by renderer contracts and prototypes."""

    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class Camera3D:
    """Camera orientation for future WEBGL-like renderers."""

    eye: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 500.0))
    target: Vec3 = field(default_factory=lambda: Vec3(0.0, 0.0, 0.0))
    up: Vec3 = field(default_factory=lambda: Vec3(0.0, 1.0, 0.0))


@dataclass(frozen=True, slots=True)
class PerspectiveProjection:
    """Perspective projection described in p5-style degrees."""

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
    bool | int | float | Vec3 | tuple[float, ...] | tuple[tuple[float, ...], ...]
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


@dataclass(frozen=True, slots=True)
class Mesh3D:
    """Indexed mesh data in logical model coordinates."""

    vertices: tuple[Vec3, ...]
    faces: tuple[tuple[int, ...], ...]
    normals: tuple[Vec3, ...] = ()
    texcoords: tuple[tuple[float, float], ...] = ()
    material: Material3D | None = None


@dataclass(frozen=True, slots=True)
class Model3D:
    """Loaded or generated model made of one or more meshes."""

    meshes: tuple[Mesh3D, ...]
    source: Path | None = None


@dataclass(frozen=True, slots=True)
class Shader3D:
    """Python-native shader description for a future OpenGL-style backend."""

    vertex_source: str
    fragment_source: str
    uniforms: Mapping[str, ShaderUniformValue] = field(default_factory=dict)
    vertex_path: Path | None = None
    fragment_path: Path | None = None


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
]
