"""Canvas, lifecycle, timing, and diagnostics forwards for object sketches."""

from __future__ import annotations

from typing import Any

from gummysnake import constants as c
from gummysnake._fast_draw import FastDrawScope
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

    def resize_canvas(self, width: int, height: int, *, pixel_density: float | None = None) -> None:
        self._ctx.resize_canvas(width, height, pixel_density=pixel_density)

    def pixel_density(self, value: float | None = None) -> float:
        return self._ctx.pixel_density(value)

    def display_density(self) -> float:
        return self._ctx.display_density()

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
