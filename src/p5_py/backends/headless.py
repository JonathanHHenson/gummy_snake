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
        blend_modes=frozenset({c.BLEND, c.REPLACE}),
    )

    def __init__(self) -> None:
        self.renderer = PillowRenderer()
        self._running = False

    def create_canvas(self, width: int, height: int, pixel_density: float = 1.0) -> None:
        self.renderer.resize(width, height, pixel_density)

    def resize_canvas(self, width: int, height: int, pixel_density: float = 1.0) -> None:
        self.renderer.resize(width, height, pixel_density)

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
