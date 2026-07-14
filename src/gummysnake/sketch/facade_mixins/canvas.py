"""Canvas, lifecycle, timing, and diagnostics forwards for object sketches."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from gummysnake import constants as c
from gummysnake.assets.gpu import (
    ComputeShader,
    Number,
    StorageBuffer,
    WebGpuContextInfo,
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
    gpu_resource_diagnostics as _gpu_resource_diagnostics,
)
from gummysnake.assets.gpu import (
    read_storage_buffer as _read_storage_buffer,
)
from gummysnake.assets.gpu import (
    reset_gpu_resource_diagnostics as _reset_gpu_resource_diagnostics,
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
from gummysnake.fast_draw_runtime import FastDrawScope
from gummysnake.sketch.facade_mixins.base import SketchFacadeBaseMixin


class SketchFacadeCanvasMixin(SketchFacadeBaseMixin):
    def no_loop(self) -> None:
        self._ctx.no_loop()

    def loop(self) -> None:
        self._ctx.loop()

    def redraw(self) -> None:
        self._ctx.redraw()

    def is_looping(self) -> bool:
        return self._ctx.is_looping()

    def frame_rate(self, value: float | None = None) -> float:
        return self._ctx.frame_rate(value)

    def millis(self) -> float:
        return self._ctx.millis()

    def create_canvas(
        self,
        width: int,
        height: int,
        renderer: c.RendererMode = c.P2D,
        *,
        pixel_density: float | None = None,
    ) -> None:
        self._ctx.create_canvas(width, height, renderer=renderer, pixel_density=pixel_density)

    def create_graphics(
        self,
        width: int,
        height: int,
        renderer: c.RendererMode = c.P2D,
        *,
        pixel_density: float | None = None,
    ) -> Graphics:
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
        return _create_framebuffer(
            width, height, renderer=renderer, pixel_density=pixel_density, depth=depth
        )

    def create_storage_buffer(
        self, data: Iterable[Number] | int, *, dtype: str = "float"
    ) -> StorageBuffer:
        return _create_storage_buffer(data, dtype=dtype)

    def update_storage_buffer(
        self, buffer: StorageBuffer, data: Iterable[Number], *, offset: int = 0
    ) -> None:
        _update_storage_buffer(buffer, data, offset=offset)

    def read_storage_buffer(self, buffer: StorageBuffer) -> tuple[Number, ...]:
        return _read_storage_buffer(buffer)

    def create_compute_shader(self, *args: Any, **kwargs: Any) -> ComputeShader:
        return _create_compute_shader(*args, **kwargs)

    def dispatch_compute(
        self, shader: ComputeShader, x: int, y: int = 1, z: int = 1, **buffers: StorageBuffer
    ) -> None:
        _dispatch_compute(shader, x, y, z, **buffers)

    def webgpu_context(self) -> WebGpuContextInfo:
        return _webgpu_context()

    def gpu_resource_diagnostics(self) -> dict[str, int]:
        return _gpu_resource_diagnostics()

    def reset_gpu_resource_diagnostics(self) -> None:
        _reset_gpu_resource_diagnostics()

    def resize_canvas(self, width: int, height: int, *, pixel_density: float | None = None) -> None:
        self._ctx.resize_canvas(width, height, pixel_density=pixel_density)

    def pixel_density(self, value: float | None = None) -> float:
        return self._ctx.pixel_density(value)

    def display_density(self) -> float:
        return self._ctx.display_density()

    def fullscreen(self, value: bool | None = None) -> bool:
        if value is not None:
            requested = bool(value)
            callback = getattr(self._ctx.backend, "set_fullscreen", None)
            if callable(callback):
                requested = bool(callback(requested))
            self._ctx._fullscreen = requested
        return bool(self._ctx._fullscreen)

    def focused(self) -> bool:
        callback = getattr(self._ctx.backend, "focused", None)
        if callable(callback):
            self._ctx._focused = bool(callback())
        return bool(self._ctx._focused)

    def cursor(self, kind: str | None = None) -> str | None:
        if kind is not None:
            self._ctx._cursor_kind = str(kind)
            self._ctx._cursor_visible = True
            callback = getattr(self._ctx.backend, "set_cursor", None)
            if callable(callback):
                callback(self._ctx._cursor_kind)
        return self._ctx._cursor_kind

    def no_cursor(self) -> None:
        self._ctx._cursor_visible = False
        callback = getattr(self._ctx.backend, "set_cursor_visible", None)
        if callable(callback):
            callback(False)

    def fast(self) -> FastDrawScope:
        return self._ctx.fast()

    def enable_performance_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        self._ctx.enable_performance_diagnostics(enabled, reset=reset)

    def reset_performance_diagnostics(self) -> None:
        self._ctx.reset_performance_diagnostics()

    def performance_diagnostics(self) -> dict[str, Any]:
        return self._ctx.performance_diagnostics()

    def renderer_performance_counters(self) -> dict[str, Any]:
        return self._ctx.renderer_performance_counters()

    def reset_renderer_performance_counters(self) -> None:
        self._ctx.reset_renderer_performance_counters()

    def enable_frame_pacing_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        self._ctx.enable_frame_pacing_diagnostics(enabled, reset=reset)

    def frame_pacing_diagnostics(self) -> dict[str, Any]:
        return self._ctx.frame_pacing_diagnostics()

    def reset_frame_pacing_diagnostics(self) -> None:
        self._ctx.reset_frame_pacing_diagnostics()

    @property
    def width(self) -> int:
        return self._ctx.width

    @property
    def height(self) -> int:
        return self._ctx.height

    @property
    def frame_count(self) -> int:
        return self._ctx.frame_count

    @property
    def delta_time(self) -> float:
        return self._ctx.delta_time
