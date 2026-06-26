"""Renderer protocol extension for 3D-capable backends."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from gummysnake.drawing.renderer import Renderer
from gummysnake.drawing.renderer3d.materials import Light3D, Material3D, Texture3D
from gummysnake.drawing.renderer3d.mesh import Mesh3D
from gummysnake.drawing.renderer3d.model import Model3D
from gummysnake.drawing.renderer3d.shader import Shader3D, ShaderUniformValue
from gummysnake.drawing.renderer3d.types import Camera3D, Matrix4, Projection3D


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
