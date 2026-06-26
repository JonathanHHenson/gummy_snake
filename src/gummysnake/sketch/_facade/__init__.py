"""Explicit object-sketch facade mixin groups."""

from __future__ import annotations

from gummysnake.sketch._facade.base import SketchFacadeBaseMixin
from gummysnake.sketch._facade.canvas import SketchFacadeCanvasMixin
from gummysnake.sketch._facade.input import SketchFacadeInputMixin
from gummysnake.sketch._facade.media import SketchFacadeMediaMixin
from gummysnake.sketch._facade.shapes import SketchFacadeShapesMixin
from gummysnake.sketch._facade.style import SketchFacadeStyleMixin
from gummysnake.sketch._facade.three_d import SketchFacadeThreeDMixin
from gummysnake.sketch._facade.transform import SketchFacadeTransformMixin

__all__ = [
    "SketchFacadeBaseMixin",
    "SketchFacadeCanvasMixin",
    "SketchFacadeInputMixin",
    "SketchFacadeMediaMixin",
    "SketchFacadeShapesMixin",
    "SketchFacadeStyleMixin",
    "SketchFacadeThreeDMixin",
    "SketchFacadeTransformMixin",
]
