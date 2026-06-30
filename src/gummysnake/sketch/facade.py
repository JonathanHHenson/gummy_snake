"""Object-oriented sketch convenience facade methods."""

from __future__ import annotations

from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin
from gummysnake.sketch.facade_mixins.canvas import SketchFacadeCanvasMixin
from gummysnake.sketch.facade_mixins.ecs import SketchFacadeEcsMixin
from gummysnake.sketch.facade_mixins.input import SketchFacadeInputMixin
from gummysnake.sketch.facade_mixins.media import SketchFacadeMediaMixin
from gummysnake.sketch.facade_mixins.shapes import SketchFacadeShapesMixin
from gummysnake.sketch.facade_mixins.style import SketchFacadeStyleMixin
from gummysnake.sketch.facade_mixins.three_d import SketchFacadeThreeDMixin
from gummysnake.sketch.facade_mixins.transform import SketchFacadeTransformMixin


class SketchFacadeMixin(
    SketchFacadeCanvasMixin,
    SketchFacadeStyleMixin,
    SketchFacadeShapesMixin,
    SketchFacadeThreeDMixin,
    SketchFacadeTransformMixin,
    SketchFacadeMediaMixin,
    SketchFacadeInputMixin,
    SketchFacadeEcsMixin,
    SketchFacadeBaseMixin,
):
    """Explicit object-mode forwards grouped by canvas, drawing, media, and input."""


__all__ = ["SketchFacadeMixin"]
