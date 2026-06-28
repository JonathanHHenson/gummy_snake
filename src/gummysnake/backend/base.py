"""Backend protocols and capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from gummysnake import constants as c
from gummysnake.drawing.renderer import Renderer

if TYPE_CHECKING:
    from gummysnake.sketch import Sketch


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    interactive: bool = False
    headless: bool = False
    text: bool = False
    images: bool = False
    pixels: bool = True
    pixel_readback: bool = True
    pixel_update: bool = True
    canvas_export: bool = True
    mouse: bool = False
    keyboard: bool = False
    touch: bool = False
    pointer_lock: bool = False
    paths: bool = True
    transforms: bool = True
    blend_modes: frozenset[c.BlendMode] = field(default_factory=frozenset)
    three_d: bool = False
    software_three_d: bool = False
    native_three_d: bool = False
    shaders: bool = False
    native_shaders: bool = False
    sound: bool = False


class Backend(Protocol):
    name: str
    capabilities: BackendCapabilities
    renderer: Renderer

    def create_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: c.RendererMode = c.P2D,
    ) -> None:
        """Create canvas.
        
        Args:
            width: The width value. Expected type: `int`.
            height: The height value. Expected type: `int`.
            pixel_density: The pixel density value. Expected type: `float | None`. Defaults to
                `None`.
            renderer: The renderer value. Expected type: `c.RendererMode`. Defaults to `c.P2D`.
        
        Returns:
            None.
        """
        ...

    def resize_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: c.RendererMode = c.P2D,
    ) -> None:
        """Resize canvas.
        
        Args:
            width: The width value. Expected type: `int`.
            height: The height value. Expected type: `int`.
            pixel_density: The pixel density value. Expected type: `float | None`. Defaults to
                `None`.
            renderer: The renderer value. Expected type: `c.RendererMode`. Defaults to `c.P2D`.
        
        Returns:
            None.
        """
        ...

    def display_density(self) -> float: ...

    def run(self, sketch: Sketch, *, max_frames: int | None = None) -> None: ...

    def stop(self) -> None: ...

    def present(self) -> None: ...
