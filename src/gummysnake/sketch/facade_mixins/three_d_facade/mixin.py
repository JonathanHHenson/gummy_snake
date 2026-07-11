"""Stable composition module for object-mode 3D capabilities.

The focused modules separate camera/projection, controls, lighting,
materials/textures, custom geometry, built-in primitives, and models/shaders.
This module retains the established ``SketchFacadeThreeDMixin`` import path.
"""

from __future__ import annotations

from gummysnake.sketch.facade_mixins.three_d_facade.camera import SketchFacadeCameraMixin
from gummysnake.sketch.facade_mixins.three_d_facade.controls import SketchFacadeControlsMixin
from gummysnake.sketch.facade_mixins.three_d_facade.geometry import SketchFacadeGeometryMixin
from gummysnake.sketch.facade_mixins.three_d_facade.lighting import SketchFacadeLightingMixin
from gummysnake.sketch.facade_mixins.three_d_facade.materials import SketchFacadeMaterialsMixin
from gummysnake.sketch.facade_mixins.three_d_facade.models import SketchFacadeModelsMixin
from gummysnake.sketch.facade_mixins.three_d_facade.primitives import SketchFacadePrimitivesMixin


class SketchFacadeThreeDMixin(
    SketchFacadeCameraMixin,
    SketchFacadeControlsMixin,
    SketchFacadeLightingMixin,
    SketchFacadeMaterialsMixin,
    SketchFacadeGeometryMixin,
    SketchFacadePrimitivesMixin,
    SketchFacadeModelsMixin,
):
    """Stable object-mode composition of all 3D forwarding capabilities."""


__all__ = ["SketchFacadeThreeDMixin"]
