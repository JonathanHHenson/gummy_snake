"""3D camera, light, material, model, and shader forwards for object sketches."""

from __future__ import annotations

from gummysnake.drawing.renderer3d import Camera3D
from gummysnake.sketch.facade_mixins.base import ColorValue, Number
from gummysnake.sketch.facade_mixins.base import (
    SketchFacadeBaseMixin as SketchFacadeBaseMixin,
)

CameraArg = Camera3D | Number
ColorArg = ColorValue | Number
