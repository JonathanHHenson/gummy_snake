"""Regression coverage for the grouped canvas renderer and context helpers."""

from __future__ import annotations

from gummysnake.backend.canvas_renderer import CanvasRenderer
from gummysnake.backend.canvas_runtime.renderer.drawing.images import CanvasRendererImagesMixin
from gummysnake.backend.canvas_runtime.renderer.drawing.models import CanvasRendererModelsMixin
from gummysnake.backend.canvas_runtime.renderer.drawing.primitives import (
    CanvasRendererPrimitivesMixin,
)
from gummysnake.backend.canvas_runtime.renderer.drawing.text import CanvasRendererTextMixin
from gummysnake.backend.canvas_runtime.renderer.images import (
    CanvasRendererImagesMixin as LegacyImages,
)
from gummysnake.backend.canvas_runtime.renderer.models import (
    CanvasRendererModelsMixin as LegacyModels,
)
from gummysnake.backend.canvas_runtime.renderer.pixel_support.mixin import CanvasRendererPixelsMixin
from gummysnake.backend.canvas_runtime.renderer.pixels import (
    CanvasRendererPixelsMixin as LegacyPixels,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_batches import (
    flush_primitive_batch_only as legacy_flush_primitive_batch_only,
)
from gummysnake.backend.canvas_runtime.renderer.primitive_support.batches import (
    flush_primitive_batch_only,
)
from gummysnake.backend.canvas_runtime.renderer.primitives import (
    CanvasRendererPrimitivesMixin as LegacyPrimitives,
)
from gummysnake.backend.canvas_runtime.renderer.text import CanvasRendererTextMixin as LegacyText
from gummysnake.context_mixins.pixel_io import update_dirty_pixel_range as legacy_dirty_upload
from gummysnake.context_mixins.pixel_support.io import update_dirty_pixel_range
from gummysnake.context_mixins.shape_capture import end_shape as legacy_end_shape
from gummysnake.context_mixins.shape_support.capture import end_shape
from gummysnake.core.color import Color
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D
from tests.helpers.canvas_runtime.modules import FakeCanvasModule


def test_canvas_renderer_composes_grouped_drawing_mixins() -> None:
    """The public adapter remains a composition root over grouped mixins."""
    assert CanvasRendererImagesMixin in CanvasRenderer.__mro__
    assert CanvasRendererModelsMixin in CanvasRenderer.__mro__
    assert CanvasRendererPixelsMixin in CanvasRenderer.__mro__
    assert CanvasRendererPrimitivesMixin in CanvasRenderer.__mro__
    assert CanvasRendererTextMixin in CanvasRenderer.__mro__


def test_grouped_renderer_and_context_support_keep_compatibility_imports() -> None:
    """Existing internal imports remain aliases instead of duplicate implementations."""
    assert LegacyImages is CanvasRendererImagesMixin
    assert LegacyModels is CanvasRendererModelsMixin
    assert LegacyPixels is CanvasRendererPixelsMixin
    assert LegacyPrimitives is CanvasRendererPrimitivesMixin
    assert LegacyText is CanvasRendererTextMixin
    assert legacy_flush_primitive_batch_only is flush_primitive_batch_only
    assert legacy_dirty_upload is update_dirty_pixel_range
    assert legacy_end_shape is end_shape


def test_grouped_primitive_flush_preserves_native_payload_and_counters() -> None:
    """The decomposed flush submits the original payload and counter values once."""
    renderer = CanvasRenderer(FakeCanvasModule())
    renderer.resize(20, 20)
    style = StyleState(fill_color=Color(255, 0, 0, 255), stroke_color=None)

    renderer.rect(1, 2, 3, 4, style, Matrix2D.identity())
    flush_primitive_batch_only(renderer)

    canvas = renderer._canvas
    assert canvas is not None
    assert canvas.calls[-1] == (
        "batch_fill_primitives",
        [(1, 1, 2, 3, 4, 0.0, 0.0, 255, 0, 0, 255)],
        (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )
    counters = renderer.performance_counters()
    assert counters["primitive_batch_records"] == 1
    assert counters["primitive_batch_flushes"] == 1
    assert counters["primitive_batch_max_records"] == 1
    assert counters["primitive_batch_fallbacks"] == 0
