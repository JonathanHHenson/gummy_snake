"""Custom 3D geometry forwards for object-mode sketches."""

from __future__ import annotations

from collections.abc import Callable

from gummysnake.drawing.renderer3d import Mesh3D, Model3D
from gummysnake.drawing.renderer3d.types import VertexPropertyValue
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeGeometryMixin(SketchFacadeBaseMixin):
    """Build and edit custom 3D geometry through the active context."""

    __facade_doc_topic__ = "Build or edit custom geometry in this sketch's active 3D scene."

    def create_model(self, mesh: Mesh3D | Model3D) -> Model3D:
        return self._ctx.create_model(mesh)

    def normal(self, x: float, y: float, z: float) -> None:
        self._ctx.normal(x, y, z)

    def vertex_property(self, name: str, value: VertexPropertyValue) -> None:
        self._ctx.vertex_property(name, value)

    def build_geometry(self, callback: Callable[[], object]) -> Model3D:
        return self._ctx.build_geometry(callback)

    def free_geometry(self, model_value: Model3D) -> None:
        self._ctx.free_geometry(model_value)

    def flip_u(self, mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
        return self._ctx.flip_u(mesh_or_model)

    def flip_v(self, mesh_or_model: Mesh3D | Model3D) -> Mesh3D | Model3D:
        return self._ctx.flip_v(mesh_or_model)
