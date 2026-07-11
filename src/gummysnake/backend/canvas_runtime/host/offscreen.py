"""Backend-owned construction for mandatory canvas offscreen targets."""

from __future__ import annotations

from gummysnake import constants as c
from gummysnake.backend.canvas import CanvasBackend
from gummysnake.context import SketchContext
from gummysnake.plugins.registry import GLOBAL_PLUGIN_REGISTRY


class _OffscreenSketch:
    """Minimal sketch host required by an isolated ``SketchContext``."""

    context: SketchContext | None = None

    def _dispatch_callback(self, _name: str, _event: object) -> None:
        return None


class OffscreenCanvasRuntime:
    """Own the backend and context backing one native offscreen surface."""

    __slots__ = ("backend", "context")

    def __init__(
        self,
        width: int,
        height: int,
        renderer: c.RendererMode,
        *,
        pixel_density: float | None,
    ) -> None:
        """Create a headless mandatory-canvas context with isolated sketch state."""

        sketch = _OffscreenSketch()
        self.backend = CanvasBackend(headless=True)
        self.context = SketchContext(sketch, self.backend, plugins=GLOBAL_PLUGIN_REGISTRY)
        sketch.context = self.context
        self.context.create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)

    def close(self) -> None:
        """Release the canvas backend resources for this offscreen surface."""

        self.backend.stop()


__all__ = ["OffscreenCanvasRuntime"]
