"""Interactive 3D control forwards for object-mode sketches."""

from __future__ import annotations

from typing import overload

from gummysnake.drawing.renderer3d import Camera3D
from gummysnake.sketch.facade_mixins.base import Number, SketchFacadeBaseMixin


class SketchFacadeControlsMixin(SketchFacadeBaseMixin):
    """Configure interactive camera controls for object-mode 3D sketches."""

    __facade_doc_topic__ = "Configure interactive controls for this sketch's 3D camera."

    @overload
    def orbit_control(self) -> Camera3D: ...

    @overload
    def orbit_control(self, sensitivity_x: Number, /) -> Camera3D: ...

    @overload
    def orbit_control(self, sensitivity_x: Number, sensitivity_y: Number, /) -> Camera3D: ...

    @overload
    def orbit_control(
        self, sensitivity_x: Number, sensitivity_y: Number, sensitivity_z: Number, /
    ) -> Camera3D: ...

    def orbit_control(self, *args: Number) -> Camera3D:
        return self._ctx.orbit_control(*args)
