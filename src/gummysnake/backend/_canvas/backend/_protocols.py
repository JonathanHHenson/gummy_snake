"""Structural protocols for composed canvas backend mixins."""

from __future__ import annotations

from typing import Any, Protocol

from gummysnake.backend.base import BackendCapabilities
from gummysnake.backend.canvas_renderer import CanvasRenderer


class CanvasBackendHost(Protocol):
    renderer: CanvasRenderer
    capabilities: BackendCapabilities
    _headless: bool | None
    _interactive: bool
    _running: bool
    _frames_drawn: int
    _next_frame_time: float
    _debug: bool
    _last_idle_debug_frame: int | None
    _frame_pacing_enabled: bool
    _frame_pacing: dict[str, float | int | bool | None]

    def _open_interactive_window(self, canvas: object) -> None: ...
    def _dispatch_pending_events(self, sketch: Any) -> None: ...
    def _record_pacing_duration(self, *args: Any, **kwargs: Any) -> None: ...
    def _record_present_interval(self, *args: Any, **kwargs: Any) -> None: ...
    def stop(self) -> None: ...

    @staticmethod
    def _sketch_context(sketch: Any) -> Any: ...

    @staticmethod
    def _perf_counter() -> float: ...

    @staticmethod
    def _sleep(delay: float) -> None: ...
