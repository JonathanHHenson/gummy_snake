"""Canvas, lifecycle, timing, and diagnostics forwards for object sketches."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from gummysnake import constants as c
from gummysnake._fast_draw import FastDrawScope
from gummysnake.assets.gpu import (
    ComputeShader,
    Number,
    StorageBuffer,
)
from gummysnake.assets.gpu import (
    create_compute_shader as _create_compute_shader,
)
from gummysnake.assets.gpu import (
    create_storage_buffer as _create_storage_buffer,
)
from gummysnake.assets.gpu import (
    dispatch_compute as _dispatch_compute,
)
from gummysnake.assets.gpu import (
    read_storage_buffer as _read_storage_buffer,
)
from gummysnake.assets.gpu import (
    update_storage_buffer as _update_storage_buffer,
)
from gummysnake.assets.gpu import (
    webgpu_context as _webgpu_context,
)
from gummysnake.assets.graphics import (
    Framebuffer,
    Graphics,
)
from gummysnake.assets.graphics import (
    create_framebuffer as _create_framebuffer,
)
from gummysnake.assets.graphics import (
    create_graphics as _create_graphics,
)
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeCanvasMixin(SketchFacadeBaseMixin):
    """Public SketchFacadeCanvasMixin value."""
    def no_loop(self) -> None:
        """Disable loop.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.no_loop()

    def loop(self) -> None:
        """Loop for this SketchFacadeCanvasMixin.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.loop()

    def redraw(self) -> None:
        """Redraw for this SketchFacadeCanvasMixin.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.redraw()

    def is_looping(self) -> bool:
        """Return whether looping is active.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        return self._ctx.is_looping()

    def frame_rate(self, value: float | None = None) -> float:
        """Frame rate for this SketchFacadeCanvasMixin.
        
        Args:
            value: The value value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.frame_rate(value)

    def millis(self) -> float:
        """Millis for this SketchFacadeCanvasMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.millis()

    def create_canvas(
        self,
        width: int,
        height: int,
        renderer: c.RendererMode = c.P2D,
        *,
        pixel_density: float | None = None,
    ) -> None:
        """Create the sketch canvas with the requested size and renderer.
        
        Args:
            width: The width value. Expected type: `int`.
            height: The height value. Expected type: `int`.
            renderer: The renderer value. Expected type: `c.RendererMode`. Defaults to `c.P2D`.
            pixel_density: The pixel density value. Expected type: `float | None`. Defaults to
                `None`.
        
        Returns:
            None.
        """
        self._ctx.create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)

    def create_graphics(
        self,
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
            pixel_density: The pixel density value. Expected type: `float | None`. Defaults to
                `None`.
        
        Returns:
            The return value. Type: `Graphics`.
        """
        return _create_graphics(width, height, renderer=renderer, pixel_density=pixel_density)

    def create_framebuffer(
        self,
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
            pixel_density: The pixel density value. Expected type: `float | None`. Defaults to
                `None`.
            depth: The depth value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            The return value. Type: `Framebuffer`.
        """
        return _create_framebuffer(
            width, height, renderer=renderer, pixel_density=pixel_density, depth=depth
        )

    def create_storage_buffer(
        self, data: Iterable[Number] | int, *, dtype: str = "float"
    ) -> StorageBuffer:
        """Create and return a storage buffer value.
        
        Args:
            data: The data value. Expected type: `Iterable[Number] | int`.
            dtype: The dtype value. Expected type: `str`. Defaults to `'float'`.
        
        Returns:
            The return value. Type: `StorageBuffer`.
        """
        return _create_storage_buffer(data, dtype=dtype)

    def update_storage_buffer(
        self, buffer: StorageBuffer, data: Iterable[Number], *, offset: int = 0
    ) -> None:
        """Update storage buffer for this SketchFacadeCanvasMixin.
        
        Args:
            buffer: The buffer value. Expected type: `StorageBuffer`.
            data: The data value. Expected type: `Iterable[Number]`.
            offset: The offset value. Expected type: `int`. Defaults to `0`.
        
        Returns:
            None.
        """
        _update_storage_buffer(buffer, data, offset=offset)

    def read_storage_buffer(self, buffer: StorageBuffer) -> tuple[Number, ...]:
        """Read storage buffer for this SketchFacadeCanvasMixin.
        
        Args:
            buffer: The buffer value. Expected type: `StorageBuffer`.
        
        Returns:
            The return value. Type: `tuple[Number, ...]`.
        """
        return _read_storage_buffer(buffer)

    def create_compute_shader(self, *args: Any, **kwargs: Any) -> ComputeShader:
        """Create and return a compute shader value.
        
        Args:
            *args: Additional positional arguments. Expected type: `Any`.
            **kwargs: Additional keyword arguments. Expected type: `Any`.
        
        Returns:
            The return value. Type: `ComputeShader`.
        """
        return _create_compute_shader(*args, **kwargs)

    def dispatch_compute(
        self, shader: ComputeShader, x: int, y: int = 1, z: int = 1, **buffers: StorageBuffer
    ) -> None:
        """Dispatch compute for this SketchFacadeCanvasMixin.
        
        Args:
            shader: The shader value. Expected type: `ComputeShader`.
            x: The x value. Expected type: `int`.
            y: The y value. Expected type: `int`. Defaults to `1`.
            z: The z value. Expected type: `int`. Defaults to `1`.
            **buffers: Additional keyword arguments. Expected type: `StorageBuffer`.
        
        Returns:
            None.
        """
        _dispatch_compute(shader, x, y, z, **buffers)

    def webgpu_context(self) -> dict[str, object]:
        """Webgpu context for this SketchFacadeCanvasMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `dict[str, object]`.
        """
        return _webgpu_context()

    def resize_canvas(self, width: int, height: int, *, pixel_density: float | None = None) -> None:
        """Resize the active sketch canvas.
        
        Args:
            width: The width value. Expected type: `int`.
            height: The height value. Expected type: `int`.
            pixel_density: The pixel density value. Expected type: `float | None`. Defaults to
                `None`.
        
        Returns:
            None.
        """
        self._ctx.resize_canvas(width, height, pixel_density=pixel_density)

    def pixel_density(self, value: float | None = None) -> float:
        """Get or set the active canvas pixel density.
        
        Args:
            value: The value value. Expected type: `float | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.pixel_density(value)

    def display_density(self) -> float:
        """Return the native display density when available.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.display_density()

    def fullscreen(self, value: bool | None = None) -> bool:
        """Fullscreen for this SketchFacadeCanvasMixin.
        
        Args:
            value: The value value. Expected type: `bool | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `bool`.
        """
        if value is not None:
            requested = bool(value)
            callback = getattr(self._ctx.backend, "set_fullscreen", None)
            if callable(callback):
                requested = bool(callback(requested))
            self._ctx._fullscreen = requested
        return bool(self._ctx._fullscreen)

    def focused(self) -> bool:
        """Focused for this SketchFacadeCanvasMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `bool`.
        """
        callback = getattr(self._ctx.backend, "focused", None)
        if callable(callback):
            self._ctx._focused = bool(callback())
        return bool(self._ctx._focused)

    def cursor(self, kind: str | None = None) -> str | None:
        """Cursor for this SketchFacadeCanvasMixin.
        
        Args:
            kind: The kind value. Expected type: `str | None`. Defaults to `None`.
        
        Returns:
            The return value. Type: `str | None`.
        """
        if kind is not None:
            self._ctx._cursor_kind = str(kind)
            self._ctx._cursor_visible = True
            callback = getattr(self._ctx.backend, "set_cursor", None)
            if callable(callback):
                callback(self._ctx._cursor_kind)
        return self._ctx._cursor_kind

    def no_cursor(self) -> None:
        """Disable cursor.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx._cursor_visible = False
        callback = getattr(self._ctx.backend, "set_cursor_visible", None)
        if callable(callback):
            callback(False)

    def fast(self) -> FastDrawScope:
        """Return a frame-local fast drawing facade for dense drawing loops.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `FastDrawScope`.
        """
        return self._ctx.fast()

    def enable_performance_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        """Enable or disable sketch performance diagnostics.
        
        Args:
            enabled: The enabled value. Expected type: `bool`. Defaults to `True`.
            reset: The reset value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            None.
        """
        self._ctx.enable_performance_diagnostics(enabled, reset=reset)

    def reset_performance_diagnostics(self) -> None:
        """Reset collected sketch performance diagnostics.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.reset_performance_diagnostics()

    def performance_diagnostics(self) -> dict[str, Any]:
        """Return collected sketch performance diagnostics.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `dict[str, Any]`.
        """
        return self._ctx.performance_diagnostics()

    def renderer_performance_counters(self) -> dict[str, Any]:
        """Return renderer performance counters for the active sketch.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `dict[str, Any]`.
        """
        return self._ctx.renderer_performance_counters()

    def reset_renderer_performance_counters(self) -> None:
        """Reset renderer performance counters for the active sketch.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.reset_renderer_performance_counters()

    def enable_frame_pacing_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        """Enable or disable frame-pacing diagnostics.
        
        Args:
            enabled: The enabled value. Expected type: `bool`. Defaults to `True`.
            reset: The reset value. Expected type: `bool`. Defaults to `True`.
        
        Returns:
            None.
        """
        self._ctx.enable_frame_pacing_diagnostics(enabled, reset=reset)

    def frame_pacing_diagnostics(self) -> dict[str, Any]:
        """Return collected frame-pacing diagnostics.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `dict[str, Any]`.
        """
        return self._ctx.frame_pacing_diagnostics()

    def reset_frame_pacing_diagnostics(self) -> None:
        """Reset collected frame-pacing diagnostics.
        
        Args:
            None.
        
        Returns:
            None.
        """
        self._ctx.reset_frame_pacing_diagnostics()

    @property
    def width(self) -> int:
        """Return the logical width of the active canvas.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return self._ctx.width

    @property
    def height(self) -> int:
        """Return the logical height of the active canvas.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return self._ctx.height

    @property
    def frame_count(self) -> int:
        """Frame count for this SketchFacadeCanvasMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `int`.
        """
        return self._ctx.frame_count

    @property
    def delta_time(self) -> float:
        """Delta time for this SketchFacadeCanvasMixin.
        
        Args:
            None.
        
        Returns:
            The return value. Type: `float`.
        """
        return self._ctx.delta_time
