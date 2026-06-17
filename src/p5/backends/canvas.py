"""Experimental Rust-powered canvas backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from p5 import constants as c
from p5.backends.base import BackendCapabilities
from p5.backends.canvas_renderer import CanvasRenderer
from p5.exceptions import BackendCapabilityError
from p5.rust.canvas import canvas_health_check, require_canvas_extension

if TYPE_CHECKING:
    from p5.sketch import Sketch


class CanvasBackend:
    """Opt-in backend adapter for the ``p5_canvas`` Rust runtime."""

    name = c.CANVAS
    capabilities = BackendCapabilities(
        interactive=False,
        headless=True,
        text=False,
        images=False,
        pixels=True,
        pixel_readback=True,
        pixel_update=True,
        canvas_export=True,
        mouse=False,
        keyboard=False,
        touch=False,
        paths=True,
        transforms=True,
        blend_modes=frozenset({c.BLEND}),
        three_d=False,
        shaders=False,
        sound=False,
    )

    def __init__(self) -> None:
        self._canvas_module = require_canvas_extension()
        self.capabilities = type(self).capabilities
        self.renderer = CanvasRenderer(self._canvas_module)
        self._running = False

    def health_check(self) -> str:
        """Return the underlying Rust canvas extension health check."""

        return canvas_health_check()

    def create_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: str = c.P2D,
    ) -> None:
        self._ensure_supported_renderer(renderer)
        self.renderer.resize(width, height, 1.0 if pixel_density is None else pixel_density)

    def resize_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: str = c.P2D,
    ) -> None:
        self.create_canvas(width, height, pixel_density, renderer=renderer)

    def display_density(self) -> float:
        return self.renderer.display_density()

    def run(self, sketch: Sketch, *, max_frames: int | None = None) -> None:
        self._running = True
        frames = 1 if max_frames is None else max_frames
        for _ in range(max(0, frames)):
            if not self._running:
                break
            sketch._draw_frame()
            self.present()

    def stop(self) -> None:
        self._running = False
        self.renderer.close()

    def present(self) -> None:
        self.renderer.present()

    def _ensure_supported_renderer(self, renderer: str) -> None:
        if renderer != c.P2D:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend currently implements only the P2D renderer; "
                "use backend='pyglet' for WEBGL sketches."
            )
