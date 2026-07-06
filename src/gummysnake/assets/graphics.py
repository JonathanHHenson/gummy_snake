"""Native offscreen graphics and framebuffer targets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gummysnake import constants as c
from gummysnake.assets.image import CanvasImage, Image
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
        """Create an isolated offscreen graphics surface."""
        Image.__init__(self, int(width), int(height))
        sketch = _OffscreenSketch()
        self.backend = CanvasBackend(headless=True)
        self.context = SketchContext(sketch, self.backend, plugins=GLOBAL_PLUGIN_REGISTRY)
        sketch.context = self.context
        self.context.create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)

    @property
    def width(self) -> int:
        """Return the logical width of this offscreen surface."""

        return self.context.width

    @property
    def height(self) -> int:
        """Return the logical height of this offscreen surface."""

        return self.context.height

    @property
    def rust_image(self) -> CanvasImage:
        """Return the Rust-owned image handle for the latest snapshot."""

        return self.snapshot().rust_image

    @property
    def cache_key(self) -> int:
        """Return a stable cache key for the latest snapshot."""

        return self.snapshot().cache_key

    @property
    def version(self) -> int:
        """Return the image version for the latest snapshot."""

        return self.snapshot().version

    def snapshot(self) -> Image:
        """Copy the current offscreen canvas into an ``Image``.

        Returns:
            An image containing the offscreen surface pixels.
        """

        return self.context._canvas_image()

    def to_rgba_bytes(self) -> bytes:
        """Read the offscreen surface as raw RGBA bytes.

        Returns:
            Physical top-left-oriented RGBA bytes.
        """

        return self.context.load_pixel_bytes()

    def remove(self) -> None:
        """Stop the offscreen backend and release runtime resources."""

        self.backend.stop()

    def __getattr__(self, name: str) -> Any:
        """Forward unknown drawing methods to the offscreen sketch context."""

        return getattr(self.context, name)

    def save(self, path: str | Path) -> None:
        """Save a snapshot of the offscreen surface.

        Args:
            path: Destination image file path.
        """

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
        """Create an offscreen framebuffer with optional depth metadata."""
        self.depth = bool(depth)
        super().__init__(width, height, renderer=renderer, pixel_density=pixel_density)


def create_graphics(
    width: int,
    height: int,
    renderer: c.RendererMode = c.P2D,
    *,
    pixel_density: float | None = None,
) -> Graphics:
    """Create an offscreen graphics surface.

    Args:
        width: Logical surface width.
        height: Logical surface height.
        renderer: Renderer mode, such as ``P2D`` or ``WEBGL``.
        pixel_density: Optional physical pixel scale for the offscreen surface.

    Returns:
        A ``Graphics`` object with drawing methods and image snapshot support.
    """

    return Graphics(width, height, renderer=renderer, pixel_density=pixel_density)


def create_framebuffer(
    width: int,
    height: int,
    renderer: c.RendererMode = c.P2D,
    *,
    pixel_density: float | None = None,
    depth: bool = True,
) -> Framebuffer:
    """Create an offscreen framebuffer with optional depth metadata.

    Args:
        width: Logical framebuffer width.
        height: Logical framebuffer height.
        renderer: Renderer mode, such as ``P2D`` or ``WEBGL``.
        pixel_density: Optional physical pixel scale for the framebuffer.
        depth: Whether the framebuffer should track depth attachment intent.

    Returns:
        A ``Framebuffer`` object with drawing methods and image snapshot support.
    """

    return Framebuffer(width, height, renderer=renderer, pixel_density=pixel_density, depth=depth)


__all__ = ["Framebuffer", "Graphics", "create_framebuffer", "create_graphics"]
