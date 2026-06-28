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
        """Create an isolated offscreen graphics surface."""
        Image.__init__(self, int(width), int(height))
        sketch = _OffscreenSketch()
        self.backend = CanvasBackend(headless=True)
        self.context = SketchContext(sketch, self.backend, plugins=GLOBAL_PLUGIN_REGISTRY)
        sketch.context = self.context
        self.context.create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)

    @property
    def width(self) -> int:
        """Return this Graphics's width.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return self.context.width

    @property
    def height(self) -> int:
        """Return this Graphics's height.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return self.context.height

    @property
    def rust_image(self):
        """Rust image for this Graphics.
        
        Args:
            None.
        
        Returns:
            The rust image value.
        """
        return self.snapshot().rust_image

    @property
    def cache_key(self) -> int:
        """Cache key for this Graphics.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return self.snapshot().cache_key

    @property
    def version(self) -> int:
        """Version for this Graphics.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return self.snapshot().version

    def snapshot(self) -> Image:
        """Snapshot for this Graphics.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `Image`.
        """
        return self.context._canvas_image()

    def to_rgba_bytes(self) -> bytes:
        """Return this Graphics converted to rgba bytes.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bytes`.
        """
        return self.context.load_pixel_bytes()

    def remove(self) -> None:
        """Remove for this Graphics.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self.backend.stop()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.context, name)

    def save(self, path: str | Path) -> None:
        """Save for this Graphics.
        
        Args:
            path: The path value. Expected type: `str | Path`.
        
        Returns:
            None.
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
    """Create and return a graphics value.
    
    Args:
        width: The width value. Expected type: `int`.
        height: The height value. Expected type: `int`.
        renderer: The renderer value. Expected type: `c.RendererMode`. Defaults to `c.P2D`.
        pixel_density: The pixel density value. Expected type: `float | None`. Defaults to `None`.
    
    Returns:
        The return value. Type: `Graphics`.
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
    """Create and return a framebuffer value.
    
    Args:
        width: The width value. Expected type: `int`.
        height: The height value. Expected type: `int`.
        renderer: The renderer value. Expected type: `c.RendererMode`. Defaults to `c.P2D`.
        pixel_density: The pixel density value. Expected type: `float | None`. Defaults to `None`.
        depth: The depth value. Expected type: `bool`. Defaults to `True`.
    
    Returns:
        The return value. Type: `Framebuffer`.
    """
    return Framebuffer(width, height, renderer=renderer, pixel_density=pixel_density, depth=depth)


__all__ = ["Framebuffer", "Graphics", "create_framebuffer", "create_graphics"]
