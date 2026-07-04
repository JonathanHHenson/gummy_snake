"""Canvas lifecycle, diagnostics, and timing methods for SketchContext."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from gummysnake import constants as c
from gummysnake._fast_draw import FastDrawScope
from gummysnake.context_mixins._protocols import SketchContextHost
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError

if TYPE_CHECKING:
    from gummysnake.context import SketchContext

_PERFORMANCE_DIAGNOSTIC_MESSAGE_LIMIT = 64

_PERFORMANCE_DIAGNOSTIC_MESSAGES = {
    "cpu_compositing_fallback": (
        "CPU compositing fallback: this operation reads the canvas into a Python Image "
        "and writes pixels back. Prefer renderer-native drawing APIs in animation loops."
    ),
    "pixel_list_conversion": (
        "Pixel list conversion: this path materializes RGBA bytes as a Python list. "
        "Use load_pixel_bytes() when a bytes-like buffer is enough."
    ),
    "pixel_readback": (
        "Pixel readback: this operation reads the current canvas pixels back to Python. "
        "Avoid it per frame unless the sketch really needs pixel data."
    ),
    "pixel_upload": (
        "Pixel upload: this operation sends a full RGBA buffer back to the canvas. "
        "Use bytes-like inputs for lower Python overhead."
    ),
    "pixel_region_upload": (
        "Pixel region upload: this operation sends only the dirty PixelBuffer region "
        "back to the canvas."
    ),
    "gpu_region_effect_pass": (
        "GPU region effect: this operation runs as an ordered canvas effect pass."
    ),
    "pixel_noop_upload_skip": (
        "Pixel upload skipped: the payload was the exact fresh load_pixel_bytes() result."
    ),
    "texture_cache_hit": "Image texture cache hit: the image version was already seen.",
    "texture_upload": (
        "Texture upload/cache miss: the image was new or mutated since the last draw. "
        "Reuse Image objects and avoid update_pixels() on images drawn every frame."
    ),
}


class CanvasContextMixin:
    backend: Any
    renderer: Any
    state: Any
    _frame_mouse_dx: float
    _frame_mouse_dy: float
    _frame_scroll_x: float
    _frame_scroll_y: float
    _lights3d: list[Any]
    _lights3d_style_stack: list[list[Any]]
    _performance_diagnostics_enabled: bool
    _performance_diagnostic_counts: dict[str, int]
    _performance_diagnostic_messages: list[str]
    _performance_diagnostic_image_versions: dict[int, int]

    @property
    def width(self) -> int:
        """Width.

        Args:
            None.

        Returns:
            The return value. Type: `int`.
        """
        return self.state.canvas.width

    @property
    def height(self) -> int:
        """Height.

        Args:
            None.

        Returns:
            The return value. Type: `int`.
        """
        return self.state.canvas.height

    @property
    def frame_count(self) -> int:
        """Frame count.

        Args:
            None.

        Returns:
            The return value. Type: `int`.
        """
        return self.state.timing.frame_count

    @property
    def delta_time(self) -> float:
        """Delta time.

        Args:
            None.

        Returns:
            The return value. Type: `float`.
        """
        return self.state.timing.delta_time

    @property
    def mouse_x(self) -> float:
        """Mouse x.

        Args:
            None.

        Returns:
            The return value. Type: `float`.
        """
        return self.state.input.mouse_x

    @property
    def mouse_y(self) -> float:
        """Mouse y.

        Args:
            None.

        Returns:
            The return value. Type: `float`.
        """
        return self.state.input.mouse_y

    def create_canvas(
        self,
        width: int,
        height: int,
        renderer: c.RendererMode = c.P2D,
        *,
        pixel_density: float | None = None,
    ) -> None:
        """Create canvas.

        Args:
            width: The width value. Expected type: `int`.
            height: The height value. Expected type: `int`.
            renderer: The renderer value. Expected type: `c.RendererMode`. Defaults to `c.P2D`.
            pixel_density: The pixel density value. Expected type: `float | None`. Defaults to
                `None`.

        Returns:
            None.
        """
        if renderer not in {c.P2D, c.WEBGL, c.WEBGPU}:
            raise ArgumentValidationError(f"Unsupported renderer {renderer!r}.")
        if renderer in {c.WEBGL, c.WEBGPU} and not self.backend.capabilities.three_d:
            raise BackendCapabilityError(
                f"Backend {self.backend.name!r} does not support renderer={renderer!r}."
            )
        self.backend.create_canvas(int(width), int(height), pixel_density, renderer=renderer)
        self.renderer = self.backend.renderer
        self.state.canvas.renderer = renderer
        if renderer in {c.WEBGL, c.WEBGPU}:
            cast(SketchContextHost, self)._reset_3d_state()
        self._sync_canvas_state()
        sync_style = getattr(self.renderer, "set_current_style", None)
        if callable(sync_style):
            sync_style(self.state.style)
        sync_matrix = getattr(self.renderer, "set_current_matrix", None)
        if callable(sync_matrix):
            sync_matrix(self.state.transform.matrix)
        self.state.canvas.created = True

    def resize_canvas(self, width: int, height: int, *, pixel_density: float | None = None) -> None:
        """Resize canvas.

        Args:
            width: The width value. Expected type: `int`.
            height: The height value. Expected type: `int`.
            pixel_density: The pixel density value. Expected type: `float | None`. Defaults to
                `None`.

        Returns:
            None.
        """
        density = self.state.canvas.pixel_density if pixel_density is None else pixel_density
        self.backend.resize_canvas(
            int(width), int(height), float(density), renderer=self.state.canvas.renderer
        )
        self.renderer = self.backend.renderer
        self._sync_canvas_state()
        sync_style = getattr(self.renderer, "set_current_style", None)
        if callable(sync_style):
            sync_style(self.state.style)
        sync_matrix = getattr(self.renderer, "set_current_matrix", None)
        if callable(sync_matrix):
            sync_matrix(self.state.transform.matrix)
        self.state.canvas.created = True

    def ensure_canvas(self) -> None:
        """Ensure canvas.

        Args:
            None.

        Returns:
            None.
        """
        if not self.state.canvas.created:
            self.create_canvas(
                self.state.canvas.width,
                self.state.canvas.height,
                renderer=self.state.canvas.renderer,
            )

    def pixel_density(self, value: float | None = None) -> float:
        """Pixel density.

        Args:
            value: The value value. Expected type: `float | None`. Defaults to `None`.

        Returns:
            The return value. Type: `float`.
        """
        if value is None:
            return self.state.canvas.pixel_density
        if value <= 0:
            raise ArgumentValidationError("pixel_density() must be positive.")
        self.resize_canvas(self.state.canvas.width, self.state.canvas.height, pixel_density=value)
        return self.state.canvas.pixel_density

    def display_density(self) -> float:
        """Display density.

        Args:
            None.

        Returns:
            The return value. Type: `float`.
        """
        return self.backend.display_density()

    def fast(self) -> FastDrawScope:
        """Fast.

        Args:
            None.

        Returns:
            The return value. Type: `FastDrawScope`.
        """
        return FastDrawScope(cast("SketchContext", self))

    def enable_performance_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        """Enable performance diagnostics.

        Args:
            enabled: The enabled value. Expected type: `bool`. Defaults to `True`.
            reset: The reset value. Expected type: `bool`. Defaults to `True`.

        Returns:
            None.
        """
        self._performance_diagnostics_enabled = bool(enabled)
        if reset:
            self.reset_performance_diagnostics()

    def reset_performance_diagnostics(self) -> None:
        """Reset performance diagnostics.

        Args:
            None.

        Returns:
            None.
        """
        self._performance_diagnostic_counts.clear()
        self._performance_diagnostic_messages.clear()
        self._performance_diagnostic_image_versions.clear()

    def performance_diagnostics(self) -> dict[str, Any]:
        """Performance diagnostics.

        Args:
            None.

        Returns:
            The return value. Type: `dict[str, Any]`.
        """
        return {
            "enabled": self._performance_diagnostics_enabled,
            "counters": dict(self._performance_diagnostic_counts),
            "messages": list(self._performance_diagnostic_messages),
            "renderer": self.renderer_performance_counters(),
        }

    def renderer_performance_counters(self) -> dict[str, Any]:
        """Renderer performance counters.

        Args:
            None.

        Returns:
            The return value. Type: `dict[str, Any]`.
        """
        callback = getattr(self.renderer, "performance_counters", None)
        if callable(callback):
            counters = callback()
            if isinstance(counters, dict):
                return counters
        return {}

    def reset_renderer_performance_counters(self) -> None:
        """Reset renderer performance counters.

        Args:
            None.

        Returns:
            None.
        """
        callback = getattr(self.renderer, "reset_performance_counters", None)
        if callable(callback):
            callback()

    def enable_frame_pacing_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        """Enable frame pacing diagnostics.

        Args:
            enabled: The enabled value. Expected type: `bool`. Defaults to `True`.
            reset: The reset value. Expected type: `bool`. Defaults to `True`.

        Returns:
            None.
        """
        callback = getattr(self.backend, "enable_frame_pacing_diagnostics", None)
        if callable(callback):
            callback(enabled, reset=reset)

    def frame_pacing_diagnostics(self) -> dict[str, Any]:
        """Frame pacing diagnostics.

        Args:
            None.

        Returns:
            The return value. Type: `dict[str, Any]`.
        """
        callback = getattr(self.backend, "frame_pacing_diagnostics", None)
        if callable(callback):
            report = callback()
            if isinstance(report, dict):
                return report
        return {}

    def reset_frame_pacing_diagnostics(self) -> None:
        """Reset frame pacing diagnostics.

        Args:
            None.

        Returns:
            None.
        """
        callback = getattr(self.backend, "reset_frame_pacing_diagnostics", None)
        if callable(callback):
            callback()

    def _record_performance_diagnostic(self, name: str) -> None:
        if not self._performance_diagnostics_enabled:
            return
        self._performance_diagnostic_counts[name] = (
            self._performance_diagnostic_counts.get(name, 0) + 1
        )
        message = _PERFORMANCE_DIAGNOSTIC_MESSAGES.get(name)
        if (
            message is not None
            and message not in self._performance_diagnostic_messages
            and len(self._performance_diagnostic_messages) < _PERFORMANCE_DIAGNOSTIC_MESSAGE_LIMIT
        ):
            self._performance_diagnostic_messages.append(message)

    def begin_frame(self) -> None:
        """Begin frame.

        Args:
            None.

        Returns:
            None.
        """
        if self.state.canvas.renderer in {c.WEBGL, c.WEBGPU}:
            self._lights3d = []
            self._lights3d_style_stack = []

    def end_frame(self) -> None:
        """End frame.

        Args:
            None.

        Returns:
            None.
        """
        self._frame_mouse_dx = 0.0
        self._frame_mouse_dy = 0.0
        self._frame_scroll_x = 0.0
        self._frame_scroll_y = 0.0

    def _sync_canvas_state(self) -> None:
        self.state.rust.sync_canvas(
            int(self.renderer.width),
            int(self.renderer.height),
            int(self.renderer.physical_width),
            int(self.renderer.physical_height),
            float(self.renderer.pixel_density),
            self.state.canvas.renderer.value,
            self.state.canvas.created,
        )

    def frame_rate(self, value: float | None = None) -> float:
        """Frame rate.

        Args:
            value: The value value. Expected type: `float | None`. Defaults to `None`.

        Returns:
            The return value. Type: `float`.
        """
        if value is not None:
            if value <= 0:
                raise ArgumentValidationError("frame_rate() must be positive.")
            self.state.timing.target_frame_rate = float(value)
        return self.state.timing.target_frame_rate

    def millis(self) -> float:
        """Millis.

        Args:
            None.

        Returns:
            The return value. Type: `float`.
        """
        return self.state.timing.millis()

    def no_loop(self) -> None:
        """No loop.

        Args:
            None.

        Returns:
            None.
        """
        self.state.looping = False

    def loop(self) -> None:
        """Loop.

        Args:
            None.

        Returns:
            None.
        """
        self.state.looping = True

    def redraw(self) -> None:
        """Redraw.

        Args:
            None.

        Returns:
            None.
        """
        self.state.redraw_requested = True

    def is_looping(self) -> bool:
        """Is looping.

        Args:
            None.

        Returns:
            The return value. Type: `bool`.
        """
        return self.state.looping
