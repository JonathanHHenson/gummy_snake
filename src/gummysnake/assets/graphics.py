"""Native offscreen graphics and framebuffer targets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gummysnake import constants as c
from gummysnake.assets.image import Image
from gummysnake.backend.canvas import CanvasBackend
from gummysnake.context import SketchContext
from gummysnake.plugins.registry import GLOBAL_PLUGIN_REGISTRY


class _OffscreenSketch:
    context: SketchContext | None = None

    def _dispatch_callback(self, _name: str, _event: object) -> None:
        return None


class Graphics(Image):
    """Offscreen canvas with isolated style, transform, pixels, and 3D state."""

    __slots__ = ("backend", "context")

    def __init__(
        self,
        width: int,
        height: int,
        renderer: c.RendererMode = c.P2D,
        *,
        pixel_density: float | None = None,
    ) -> None:
        Image.__init__(self, int(width), int(height))
        sketch = _OffscreenSketch()
        self.backend = CanvasBackend(headless=True)
        self.context = SketchContext(sketch, self.backend, plugins=GLOBAL_PLUGIN_REGISTRY)
        sketch.context = self.context
        self.context.create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)

    @property
    def width(self) -> int:
        return self.context.width

    @property
    def height(self) -> int:
        return self.context.height

    @property
    def rust_image(self):
        return self.snapshot().rust_image

    @property
    def cache_key(self) -> int:
        return self.snapshot().cache_key

    @property
    def version(self) -> int:
        return self.snapshot().version

    def snapshot(self) -> Image:
        return self.context._canvas_image()

    def to_rgba_bytes(self) -> bytes:
        return self.context.load_pixel_bytes()

    def remove(self) -> None:
        self.backend.stop()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.context, name)

    def save(self, path: str | Path) -> None:
        self.snapshot().save(path)


class Framebuffer(Graphics):
    """Offscreen framebuffer with optional depth attachment metadata."""

    __slots__ = ("depth",)

    def __init__(
        self,
        width: int,
        height: int,
        renderer: c.RendererMode = c.P2D,
        *,
        pixel_density: float | None = None,
        depth: bool = True,
    ) -> None:
        self.depth = bool(depth)
        super().__init__(width, height, renderer=renderer, pixel_density=pixel_density)


def create_graphics(
    width: int,
    height: int,
    renderer: c.RendererMode = c.P2D,
    *,
    pixel_density: float | None = None,
) -> Graphics:
    return Graphics(width, height, renderer=renderer, pixel_density=pixel_density)


def create_framebuffer(
    width: int,
    height: int,
    renderer: c.RendererMode = c.P2D,
    *,
    pixel_density: float | None = None,
    depth: bool = True,
) -> Framebuffer:
    return Framebuffer(width, height, renderer=renderer, pixel_density=pixel_density, depth=depth)


__all__ = ["Framebuffer", "Graphics", "create_framebuffer", "create_graphics"]
