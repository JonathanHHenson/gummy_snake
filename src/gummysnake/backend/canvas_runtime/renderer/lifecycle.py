"""Canvas renderer allocation and frame lifecycle helpers."""

from __future__ import annotations

from typing import Any, Protocol, cast

from gummysnake import constants as c
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.exceptions import ArgumentValidationError


class _LifecycleHost(Protocol):
    _canvas: Any | None
    _abort_frame_on_native_close: bool
    _skip_canvas_end_frame: bool
    _clip_depth: int
    renderer_mode: c.RendererMode

    def _canvas_type(self) -> type[Any]: ...
    def _sync_dimensions(self) -> None: ...
    def _require_canvas(self) -> Any: ...
    def _pump_native_events_if_due(self, *, force: bool = False) -> bool: ...
    def _should_close(self) -> bool: ...
    def _count(self, name: str, amount: int = 1) -> None: ...


class CanvasRendererLifecycleMixin:
    width: int
    height: int
    physical_width: int
    physical_height: int
    pixel_density: float
    _rust_transform_synced: bool
    _rust_style_synced: bool

    def resize(
        self,
        width: int,
        height: int,
        pixel_density: float = 1.0,
        *,
        mode: str = "headless",
        renderer: c.RendererMode = c.P2D,
    ) -> None:
        host = cast(_LifecycleHost, self)
        cast(CanvasRendererHost, self)._flush_line_batch()
        canvas_type = host._canvas_type()
        host.renderer_mode = renderer
        try:
            if host._canvas is None:
                host._canvas = canvas_type(width, height, pixel_density, mode, c.P2D)
            else:
                host._canvas.resize(width, height, pixel_density, c.P2D)
            host._sync_dimensions()
            self._rust_transform_synced = True
            self._rust_style_synced = True
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc

    def resize_canvas(
        self,
        width: int,
        height: int,
        pixel_density: float = 1.0,
        renderer: c.RendererMode | None = None,
    ) -> None:
        host = cast(_LifecycleHost, self)
        cast(CanvasRendererHost, self)._flush_line_batch()
        renderer_mode = host.renderer_mode if renderer is None else renderer
        try:
            resize_canvas = getattr(host._require_canvas(), "resize_canvas", None)
            if callable(resize_canvas):
                resize_canvas(width, height, pixel_density, c.P2D)
            else:
                host._require_canvas().resize(width, height, pixel_density, c.P2D)
            host.renderer_mode = renderer_mode
            host._sync_dimensions()
            self._rust_transform_synced = True
            self._rust_style_synced = True
        except ValueError as exc:
            raise ArgumentValidationError(str(exc)) from exc

    def begin_frame(self) -> None:
        host = cast(_LifecycleHost, self)
        host._abort_frame_on_native_close = True
        host._skip_canvas_end_frame = False
        host._pump_native_events_if_due(force=True)
        host._require_canvas().begin_frame()

    def end_frame(self) -> None:
        host = cast(_LifecycleHost, self)
        try:
            renderer = cast(CanvasRendererHost, self)
            renderer._flush_line_batch_only()
            renderer._flush_primitive_batch_only()
            renderer._flush_image_batch()
            renderer._flush_model_batch()
            renderer._flush_text_batch(final=True)
            self.restore_clip_depth(0)
            if not host._skip_canvas_end_frame:
                host._require_canvas().end_frame()
        finally:
            host._abort_frame_on_native_close = False

    def present(self) -> None:
        host = cast(_LifecycleHost, self)
        cast(CanvasRendererHost, self)._flush_line_batch()
        if host._pump_native_events_if_due(force=True) or host._should_close():
            return
        host._require_canvas().present()
        host._count("frames_presented")

    def close(self) -> None:
        host = cast(_LifecycleHost, self)
        host._abort_frame_on_native_close = False
        cast(CanvasRendererHost, self)._flush_line_batch()
        if host._canvas is not None:
            host._canvas.close()

    def runtime_canvas(self) -> Any:
        return cast(_LifecycleHost, self)._require_canvas()

    def clip_depth(self) -> int:
        return cast(_LifecycleHost, self)._clip_depth

    def restore_clip_depth(self, depth: int) -> None:
        host = cast(_LifecycleHost, self)
        if depth < 0:
            raise ArgumentValidationError("Clip depth cannot be negative.")
        while host._clip_depth > depth:
            cast(CanvasRendererHost, self).end_clip()
        if host._clip_depth < depth:
            raise ArgumentValidationError("Cannot restore a deeper clip stack than is active.")
