"""Experimental Rust-powered canvas backend."""

from __future__ import annotations

import os
import time
from dataclasses import replace

from gummysnake import constants as c
from gummysnake.backend._canvas.backend.events import CanvasBackendEventsMixin
from gummysnake.backend._canvas.backend.pacing import CanvasBackendPacingMixin
from gummysnake.backend._canvas.backend.runtime import CanvasBackendRuntimeMixin
from gummysnake.backend.base import BackendCapabilities
from gummysnake.backend.canvas_renderer import CanvasRenderer
from gummysnake.exceptions import BackendCapabilityError
from gummysnake.rust.canvas import canvas_gpu_status, canvas_health_check, require_canvas_extension


class CanvasBackend(
    CanvasBackendPacingMixin,
    CanvasBackendEventsMixin,
    CanvasBackendRuntimeMixin,
):
    """Opt-in backend adapter for the ``gummy_canvas`` Rust runtime.

    The Rust canvas crate owns the pixel surface and, for native builds, the
    window/event source. The Python backend remains responsible for preserving
    the existing sketch lifecycle order and dispatching normalized events into
    ``SketchContext``.
    """

    name = "canvas"
    capabilities = BackendCapabilities(
        interactive=False,
        headless=True,
        text=True,
        images=True,
        pixels=True,
        pixel_readback=True,
        pixel_update=True,
        canvas_export=True,
        mouse=False,
        keyboard=False,
        touch=False,
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
        software_three_d=True,
        native_three_d=False,
        shaders=True,
        native_shaders=False,
        sound=True,
    )

    def __init__(self, *, headless: bool | None = None) -> None:
        self._canvas_module = require_canvas_extension()
        native_runtime = self._native_window_available()
        self.capabilities = replace(
            type(self).capabilities,
            interactive=native_runtime,
            mouse=native_runtime,
            keyboard=native_runtime,
            touch=native_runtime,
        )
        self.renderer = CanvasRenderer(self._canvas_module)
        self._headless = headless
        self._interactive = headless is False
        self._running = False
        self._frames_drawn = 0
        self._next_frame_time = 0.0
        self._debug = os.environ.get("GUMMY_CANVAS_DEBUG") == "1"
        self._last_idle_debug_frame: int | None = None
        self._frame_pacing_enabled = os.environ.get("GUMMY_CANVAS_PACING_DEBUG") == "1"
        self._frame_pacing: dict[str, float | int | bool | None] = {}
        self._last_present_time: float | None = None
        self.reset_frame_pacing_diagnostics()

    def health_check(self) -> str:
        """Return the underlying Rust canvas extension health check."""

        return canvas_health_check()

    def gpu_status(self) -> str:
        """Return an actionable GPU availability diagnostic for this canvas runtime."""

        canvas = self.renderer._canvas
        runtime_status = getattr(canvas, "gpu_status", None) if canvas is not None else None
        if callable(runtime_status):
            status = str(runtime_status())
            if status == "available":
                return status
            return (
                f"{status}; headless rendering can continue through CPU-backed canvas paths, "
                "but native interactive presentation and GPU-accelerated drawing may be "
                "disabled or slower."
            )
        return canvas_gpu_status()

    def _native_window_available(self) -> bool:
        native_window_available = getattr(self._canvas_module, "native_window_available", None)
        if callable(native_window_available):
            return bool(native_window_available())
        return False

    def create_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: c.RendererMode = c.P2D,
    ) -> None:
        self._ensure_supported_renderer(renderer)
        density = self.renderer.pixel_density if pixel_density is None else pixel_density
        self.renderer.resize(width, height, density, mode="headless")

    def resize_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: c.RendererMode = c.P2D,
    ) -> None:
        self.create_canvas(width, height, pixel_density, renderer=renderer)

    def display_density(self) -> float:
        return self.renderer.display_density()

    @staticmethod
    def _perf_counter() -> float:
        return time.perf_counter()

    @staticmethod
    def _sleep(delay: float) -> None:
        time.sleep(delay)

    def _ensure_supported_renderer(self, renderer: c.RendererMode) -> None:
        if renderer not in {c.P2D, c.WEBGL}:
            raise BackendCapabilityError(
                "The experimental 'canvas' backend currently implements only P2D and WEBGL "
                f"renderers, got {renderer!r}."
            )


__all__ = ["CanvasBackend"]
