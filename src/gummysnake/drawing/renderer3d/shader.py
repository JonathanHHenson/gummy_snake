"""Python-native 3D shader descriptions."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass, field
from pathlib import Path

from gummysnake.drawing.renderer3d.materials import Texture3D
from gummysnake.drawing.renderer3d.types import Vec3

type ShaderUniformValue = (
    bool | int | float | Vec3 | Texture3D | tuple[float, ...] | tuple[tuple[float, ...], ...]
)


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
