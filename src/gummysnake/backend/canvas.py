"""Rust-powered canvas backend."""

from __future__ import annotations

import os
import time
from dataclasses import replace

from gummysnake import constants as c
from gummysnake.backend.base import BackendCapabilities
from gummysnake.backend.canvas_renderer import CanvasRenderer
from gummysnake.backend.canvas_runtime.host.events import CanvasBackendEventsMixin
from gummysnake.backend.canvas_runtime.host.pacing import CanvasBackendPacingMixin
from gummysnake.backend.canvas_runtime.host.runtime import CanvasBackendRuntimeMixin
from gummysnake.exceptions import BackendCapabilityError
from gummysnake.rust import canvas as canvas_bridge


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
        pointer_lock=False,
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
        """Create a canvas backend using the mandatory Rust canvas runtime."""
        runtime_loader = vars(canvas_bridge)["require_canvas_runtime"]
        self._canvas_module = runtime_loader()
        native_runtime = self._native_window_available()
        self.capabilities = replace(
            type(self).capabilities,
            interactive=native_runtime,
            mouse=native_runtime,
            keyboard=native_runtime,
            touch=native_runtime,
            pointer_lock=native_runtime and self._pointer_lock_available(),
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
        self._pointer_lock_mode = "clamped"
        self.reset_frame_pacing_diagnostics()

    def health_check(self) -> str:
        """Return a short status string from the Rust canvas runtime."""

        return canvas_bridge.canvas_health_check()

    def gpu_status(self) -> str:
        """Return a human-readable GPU availability status."""

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
        return canvas_bridge.canvas_gpu_status()

    def _native_window_available(self) -> bool:
        native_window_available = getattr(self._canvas_module, "native_window_available", None)
        if callable(native_window_available):
            return bool(native_window_available())
        return False

    def _pointer_lock_available(self) -> bool:
        canvas_type = getattr(self._canvas_module, "Canvas", None)
        if canvas_type is None:
            return False
        return hasattr(canvas_type, "request_pointer_lock") and hasattr(
            canvas_type, "exit_pointer_lock"
        )

    def request_pointer_lock(self) -> bool:
        """Ask the native runtime to lock pointer movement to the canvas.

        Returns:
            ``True`` when the runtime accepted the request.
        """

        callback = getattr(self.renderer.runtime_canvas(), "request_pointer_lock", None)
        if callable(callback):
            return bool(callback())
        raise BackendCapabilityError(
            "Pointer lock requires a native canvas runtime built with pointer-lock support. "
            "Run interactively with a capable gummy_canvas build, or continue without pointer lock."
        )

    def exit_pointer_lock(self) -> bool:
        """Ask the native runtime to release pointer lock.

        Returns:
            ``True`` when the runtime accepted the request.
        """

        callback = getattr(self.renderer.runtime_canvas(), "exit_pointer_lock", None)
        if callable(callback):
            return bool(callback())
        raise BackendCapabilityError(
            "Pointer lock requires a native canvas runtime built with pointer-lock support. "
            "Run interactively with a capable gummy_canvas build, or continue without pointer lock."
        )

    def set_pointer_lock_mode(self, mode: str) -> str:
        """Set how pointer coordinates behave while pointer lock is active.

        Args:
            mode: Pointer lock mode name understood by the runtime.

        Returns:
            The mode that was stored on the backend.
        """

        self._pointer_lock_mode = mode
        canvas = self.renderer._canvas
        callback = getattr(canvas, "set_pointer_lock_mode", None) if canvas is not None else None
        if callable(callback):
            callback(mode)
        return mode

    def pointer_lock_mode(self) -> str:
        """Return the currently configured pointer-lock mode."""

        return self._pointer_lock_mode

    def start_text_input(self) -> bool:
        """Start native text-input capture for keyboard text events.

        Returns:
            ``True`` when the runtime accepted the request.
        """

        callback = getattr(self.renderer.runtime_canvas(), "start_text_input", None)
        if callable(callback):
            return bool(callback())
        raise BackendCapabilityError(
            "Text input requires a native canvas runtime built with keyboard input support."
        )

    def stop_text_input(self) -> bool:
        """Stop native text-input capture.

        Returns:
            ``True`` when the runtime accepted the request.
        """

        callback = getattr(self.renderer.runtime_canvas(), "stop_text_input", None)
        if callable(callback):
            return bool(callback())
        raise BackendCapabilityError(
            "Text input requires a native canvas runtime built with keyboard input support."
        )

    def text_input_active(self) -> bool:
        """Return whether native text-input capture is active."""

        canvas = self.renderer._canvas
        callback = getattr(canvas, "text_input_active", None) if canvas is not None else None
        return bool(callback()) if callable(callback) else False

    def create_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: c.RendererMode = c.P2D,
    ) -> None:
        """Create or reset the Rust canvas surface.

        Args:
            width: Logical canvas width.
            height: Logical canvas height.
            pixel_density: Optional logical-to-physical pixel scale.
            renderer: Requested renderer mode.
        """

        self._ensure_supported_renderer(renderer)
        density = self.renderer.pixel_density if pixel_density is None else pixel_density
        self.renderer.resize(width, height, density, mode="headless", renderer=renderer)
        self.set_pointer_lock_mode(self._pointer_lock_mode)

    def resize_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float | None = None,
        *,
        renderer: c.RendererMode = c.P2D,
    ) -> None:
        """Resize the Rust canvas surface.

        Args:
            width: New logical canvas width.
            height: New logical canvas height.
            pixel_density: Optional logical-to-physical pixel scale.
            renderer: Renderer mode to keep active after resizing.
        """

        self.create_canvas(width, height, pixel_density, renderer=renderer)

    def display_density(self) -> float:
        """Return the display scale reported by the canvas runtime."""

        return self.renderer.display_density()

    @staticmethod
    def _perf_counter() -> float:
        return time.perf_counter()

    @staticmethod
    def _sleep(delay: float) -> None:
        time.sleep(delay)

    def _ensure_supported_renderer(self, renderer: c.RendererMode) -> None:
        if renderer not in {c.P2D, c.WEBGL, c.WEBGPU}:
            raise BackendCapabilityError(
                "The canvas backend implements P2D, WEBGL, and WEBGPU-compatible "
                f"renderers, got {renderer!r}."
            )


__all__ = ["CanvasBackend"]
