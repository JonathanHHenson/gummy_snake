"""Headless backend for tests, scripts, and image export."""

from __future__ import annotations

from p5_py import constants as c
from p5_py.backends.base import BackendCapabilities
from p5_py.backends.pillow import PillowRenderer


class HeadlessBackend:
    name = c.HEADLESS
    capabilities = BackendCapabilities(
        headless=True,
        pixels=True,
        paths=True,
        transforms=True,
        blend_modes=frozenset(
            {
                c.BLEND,
                c.REPLACE,
                c.ADD,
                c.DARKEST,
                c.LIGHTEST,
                c.DIFFERENCE,
                c.EXCLUSION,
                c.MULTIPLY,
                c.SCREEN,
            }
        ),
        three_d=True,
    )

    def __init__(self) -> None:
        self.renderer = PillowRenderer()
        self._running = False

    def create_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: str = c.P2D,
    ) -> None:
        del renderer
        self.renderer.resize(width, height, 1.0 if pixel_density is None else pixel_density)

    def resize_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: str = c.P2D,
    ) -> None:
        del renderer
        self.renderer.resize(width, height, 1.0 if pixel_density is None else pixel_density)

    def display_density(self) -> float:
        return 1.0

    def run(self, sketch, *, max_frames: int | None = None) -> None:
        self._running = True
        frames = 1 if max_frames is None else max_frames
        for _ in range(max(0, frames)):
            if not self._running:
                break
            sketch._draw_frame()
            self.present()

    def stop(self) -> None:
        self._running = False

    def present(self) -> None:
        pass
