"""3D model and shader forwards for object-mode sketches."""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets.model import load_model as _load_model
from gummysnake.assets.model import load_model_async as _load_model_async
from gummysnake.assets.shader import load_shader_async as _load_shader_async
from gummysnake.drawing.renderer3d import Mesh3D, Model3D, Shader3D, ShaderUniformValue
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeModelsMixin(SketchFacadeBaseMixin):
    """Load, draw, export, and shade 3D models through the active context."""

    __facade_doc_topic__ = "Load, draw, export, or shade models in this sketch's active 3D scene."

    def load_model(
        self, path: str | Path, normalize: bool = False, *, package: str | None = None
    ) -> Model3D:
        return _load_model(path, normalize, package=package)

    async def load_model_async(
        self, path: str | Path, normalize: bool = False, *, package: str | None = None
    ) -> Model3D:
        return await _load_model_async(path, normalize, package=package)

    def model(self, shape: Mesh3D | Model3D) -> None:
        self._ctx.model(shape)

    def save_obj(self, model_value: Model3D, path: str | Path) -> Path:
        return self._ctx.save_obj(model_value, path)

    def save_stl(self, model_value: Model3D, path: str | Path) -> Path:
        return self._ctx.save_stl(model_value, path)

    def load_shader(self, vertex_path: str | Path, fragment_path: str | Path) -> Shader3D:
        return self._ctx.load_shader(vertex_path, fragment_path)

    async def load_shader_async(
        self, vertex_path: str | Path, fragment_path: str | Path
    ) -> Shader3D:
        return await _load_shader_async(vertex_path, fragment_path)

    def create_shader(self, vertex_source: str, fragment_source: str) -> Shader3D:
        return self._ctx.create_shader(vertex_source, fragment_source)

    def shader(self, shader_program: Shader3D) -> None:
        self._ctx.shader(shader_program)

    def reset_shader(self) -> None:
        self._ctx.reset_shader()

    def set_shader_uniform(self, name: str, value: ShaderUniformValue) -> None:
        self._ctx.set_shader_uniform(name, value)
