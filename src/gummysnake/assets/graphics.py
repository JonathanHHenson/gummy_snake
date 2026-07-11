"""Stable public offscreen graphics and framebuffer targets."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from gummysnake import constants as c
from gummysnake.assets.image import CanvasImage, Image
from gummysnake.backend.canvas_runtime.host.offscreen import OffscreenCanvasRuntime
from gummysnake.core.color import Color

if TYPE_CHECKING:
    from gummysnake.backend.canvas import CanvasBackend
    from gummysnake.context import SketchContext


class GraphicsDrawingSurface(Protocol):
    """Statically visible drawing operations available from ``Graphics.drawing``.

    The surface is an isolated sketch context.  It intentionally names public
    drawing operations rather than exposing a renderer implementation.
    """

    def background(self, *values: Color | str | float | int) -> None: ...

    def clear(self) -> None: ...

    def rect(self, x: float, y: float, width: float, height: float | None = None) -> None: ...

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None: ...

    def circle(self, x: float, y: float, diameter: float) -> None: ...

    def line(self, *coordinates: float) -> None: ...

    def point(self, x: float, y: float, z: float | None = None) -> None: ...

    def image(self, image: Image | CanvasImage, x: float, y: float, *args: float) -> None: ...

    def model(self, shape: object) -> None: ...

    def text(self, value: object, x: float, y: float, *bounds: float) -> None: ...

    def load_pixels(self) -> object: ...

    def update_pixels(self, pixels: object | None = None) -> None: ...

    def pixel_density(self, value: float | None = None) -> float: ...


class _GraphicsDrawingFacade:
    """Invalidate a graphics snapshot before forwarding a drawing operation."""

    __slots__ = ("_graphics",)

    def __init__(self, graphics: Graphics) -> None:
        self._graphics = graphics

    def __getattr__(self, name: str) -> Callable[..., object]:
        value = getattr(self._graphics.context, name)
        if not callable(value):
            raise AttributeError(name)

        def draw(*args: object, **kwargs: object) -> object:
            self._graphics._invalidate_snapshot()
            return value(*args, **kwargs)

        return draw


class Graphics(Image):
    """Offscreen canvas with isolated style, transform, pixels, and 3D state.

    ``drawing`` provides the typed drawing facade.  Established direct drawing
    access (for example, ``graphics.rect(...)``) remains forwarded to that same
    isolated context for compatibility.
    """

    __slots__ = ("_drawing", "_offscreen", "_snapshot")

    def __init__(
        self,
        width: int,
        height: int,
        renderer: c.RendererMode = c.P2D,
        *,
        pixel_density: float | None = None,
    ) -> None:
        """Create an isolated mandatory-canvas offscreen graphics surface."""

        Image.__init__(self, int(width), int(height))
        self._offscreen = OffscreenCanvasRuntime(
            width, height, renderer, pixel_density=pixel_density
        )
        self._snapshot: Image | None = None
        self._drawing = _GraphicsDrawingFacade(self)

    @property
    def backend(self) -> CanvasBackend:
        """Return the backend that owns this isolated offscreen runtime."""

        return self._offscreen.backend

    @property
    def context(self) -> SketchContext:
        """Return the isolated sketch context for this offscreen surface."""

        return self._offscreen.context

    @property
    def drawing(self) -> GraphicsDrawingSurface:
        """Return the statically visible offscreen drawing facade."""

        return cast(GraphicsDrawingSurface, self._drawing)

    @property
    def width(self) -> int:
        """Return the logical width of this offscreen surface."""

        return self._offscreen.context.width

    @property
    def height(self) -> int:
        """Return the logical height of this offscreen surface."""

        return self._offscreen.context.height

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
        """Copy the current offscreen canvas into a cached ``Image`` snapshot."""

        if self._snapshot is None:
            self._snapshot = self._offscreen.context._canvas_image()
        return self._snapshot

    def _invalidate_snapshot(self) -> None:
        self._snapshot = None

    def to_rgba_bytes(self) -> bytes:
        """Read the offscreen surface as physical top-left-oriented RGBA bytes."""

        return self._offscreen.context.load_pixel_bytes()

    def pixel_density(self, value: float | None = None) -> float:
        """Get or set the offscreen canvas pixel density.

        Unlike an ``Image`` snapshot, this controls the physical backing scale
        of the isolated canvas and preserves the normal canvas API behavior.
        """

        if value is not None:
            self._invalidate_snapshot()
        return self._offscreen.context.pixel_density(value)

    def remove(self) -> None:
        """Stop the offscreen backend and release runtime resources."""

        self._offscreen.close()

    def __getattr__(self, name: str) -> Callable[..., object]:
        """Forward established direct drawing calls to the isolated context.

        Use ``drawing`` for static type information.  This compatibility path
        intentionally returns a callable rather than an unconstrained ``Any``.
        """

        return getattr(self._drawing, name)

    def save(self, path: str | Path) -> None:
        """Save a snapshot of the offscreen surface."""

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
    """Create an offscreen graphics surface backed by mandatory ``gummy_canvas``."""

    return Graphics(width, height, renderer=renderer, pixel_density=pixel_density)


def create_framebuffer(
    width: int,
    height: int,
    renderer: c.RendererMode = c.P2D,
    *,
    pixel_density: float | None = None,
    depth: bool = True,
) -> Framebuffer:
    """Create an offscreen framebuffer with optional depth metadata."""

    return Framebuffer(width, height, renderer=renderer, pixel_density=pixel_density, depth=depth)


__all__ = [
    "Framebuffer",
    "Graphics",
    "GraphicsDrawingSurface",
    "create_framebuffer",
    "create_graphics",
]
