"""Renderer adapter for the experimental Rust canvas backend."""

from __future__ import annotations

from gummysnake.backend._canvas.renderer.core import (
    CanvasRendererCore,
    PerformanceCounters,
)
from gummysnake.backend._canvas.renderer.core import (
    MatrixPayload as _MatrixPayload,
)
from gummysnake.backend._canvas.renderer.core import (
    TextMetricKey as _TextMetricKey,
)
from gummysnake.backend._canvas.renderer.core import (
    color_payload as _color_payload,
)
from gummysnake.backend._canvas.renderer.core import (
    matrix_payload as _matrix_payload,
)
from gummysnake.backend._canvas.renderer.core import (
    style_payload as _style_payload,
)
from gummysnake.backend._canvas.renderer.core import (
    text_metric_key as _text_metric_key,
)
from gummysnake.backend._canvas.renderer.images import CanvasRendererImagesMixin
from gummysnake.backend._canvas.renderer.pixels import CanvasRendererPixelsMixin
from gummysnake.backend._canvas.renderer.primitives import CanvasRendererPrimitivesMixin
from gummysnake.backend._canvas.renderer.text import CanvasRendererTextMixin


class CanvasRenderer(
    CanvasRendererImagesMixin,
    CanvasRendererPixelsMixin,
    CanvasRendererTextMixin,
    CanvasRendererPrimitivesMixin,
    CanvasRendererCore,
):
    """Renderer protocol adapter for ``gummysnake.rust._canvas``.

    The adapter keeps Python-facing renderer attributes mirrored from the Rust
    canvas and translates Gummy Snake state objects into primitive bridge payloads.
    """


__all__ = [
    "CanvasRenderer",
    "PerformanceCounters",
    "_MatrixPayload",
    "_TextMetricKey",
    "_color_payload",
    "_matrix_payload",
    "_style_payload",
    "_text_metric_key",
]
