"""Sketch context containing mutable runtime state."""

from __future__ import annotations

from collections.abc import Buffer, Sequence
from typing import TYPE_CHECKING, Any

from gummysnake.context_mixins.canvas import CanvasContextMixin
from gummysnake.context_mixins.images import ImageContextMixin
from gummysnake.context_mixins.input import InputContextMixin
from gummysnake.context_mixins.pixels import PixelContextMixin
from gummysnake.context_mixins.shapes import ShapeContextMixin
from gummysnake.context_mixins.style import StyleContextMixin
from gummysnake.context_mixins.text import TextContextMixin
from gummysnake.context_mixins.three_d import ThreeDContextMixin
from gummysnake.context_mixins.transform import TransformContextMixin
from gummysnake.core.state import SketchState
from gummysnake.drawing.renderer3d import (
    Camera3D,
    Light3D,
    Material3D,
    OrthographicProjection,
    PerspectiveProjection,
    Shader3D,
)

if TYPE_CHECKING:
    from gummysnake.plugins.registry import PluginRegistry


class SketchContext(
    CanvasContextMixin,
    StyleContextMixin,
    TransformContextMixin,
    PixelContextMixin,
    InputContextMixin,
    ShapeContextMixin,
    ImageContextMixin,
    TextContextMixin,
    ThreeDContextMixin,
):
    """Mutable state and operations for one running sketch."""

    def __init__(self, sketch: Any, backend: Any, *, plugins: PluginRegistry) -> None:
        self.sketch = sketch
        self.backend = backend
        self.renderer = backend.renderer
        self.plugins = plugins
        self.state = SketchState()
        self.state.input.touch_supported = bool(backend.capabilities.touch)
        self.pixels: Sequence[int] | Buffer = []
        self._camera3d = Camera3D()
        self._projection3d: PerspectiveProjection | OrthographicProjection = PerspectiveProjection()
        self._lights3d: list[Light3D] = []
        self._material3d: Material3D | None = None
        self._normal_material3d = False
        self._material3d_style_stack: list[tuple[Material3D | None, bool]] = []
        self._frame_mouse_dx = 0.0
        self._frame_mouse_dy = 0.0
        self._frame_scroll_x = 0.0
        self._frame_scroll_y = 0.0
        self._shader3d: Shader3D | None = None
        self._spline_tightness = 0.0
        self._text_direction = "ltr"
        self._text_wrap = "word"
        self._text_weight = 400
        self._accessibility_descriptions: list[dict[str, str]] = []
        self._performance_diagnostics_enabled = False
        self._performance_diagnostic_counts: dict[str, int] = {}
        self._performance_diagnostic_messages: list[str] = []
        self._performance_diagnostic_image_versions: dict[int, int] = {}
