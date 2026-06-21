# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false, reportArgumentType=false
"""Run-loop helpers for the Rust canvas backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gummysnake.exceptions import BackendCapabilityError

if TYPE_CHECKING:
    from gummysnake.sketch import Sketch


class CanvasBackendRuntimeMixin:
    def run(self, sketch: Sketch, *, max_frames: int | None = None) -> None:
        """Run the sketch."""

        should_run_interactive = self._interactive or (
            self._headless is None
            and max_frames is None
            and self.capabilities.interactive
            and getattr(sketch, "context", None) is not None
        )
        if should_run_interactive:
            self._run_interactive(sketch, max_frames=max_frames)
        else:
            self._run_headless(sketch, max_frames=1 if max_frames is None else max_frames)

    def stop(self) -> None:
        self._running = False
        self.renderer.close()

    def present(self) -> None:
        self.renderer.present()

    def _run_headless(self, sketch: Sketch, *, max_frames: int) -> None:
        self._running = True
        for _ in range(max(0, max_frames)):
            if not self._running:
                break
            self._draw_and_present(sketch)

    def _run_interactive(self, sketch: Sketch, *, max_frames: int | None = None) -> None:
        canvas = self.renderer.runtime_canvas()
        self._open_interactive_window(canvas)
        self._running = True
        self._frames_drawn = 0
        context = self._sketch_context(sketch)
        interval = 1.0 / max(1.0, context.state.timing.target_frame_rate)
        self._next_frame_time = self._perf_counter()

        while self._running and not self._should_close(canvas):
            was_looping = context.state.looping
            self._dispatch_pending_events(sketch)
            self._wake_for_pending_draw(context, was_looping=was_looping)
            if max_frames is not None:
                if self._bounded_interactive_tick(sketch, context, max_frames):
                    break
                continue
            self._interactive_tick(sketch, context, interval)
        self.stop()

    def _bounded_interactive_tick(self, sketch: Sketch, context: Any, max_frames: int) -> bool:
        drew_frame = self._draw_and_present(sketch)
        self._debug_interactive_tick("bounded interactive tick", context, drew_frame)
        if drew_frame:
            self._frames_drawn += 1
        elif not context.state.looping and not context.state.redraw_requested:
            return True
        return self._frames_drawn >= max_frames

    def _interactive_tick(self, sketch: Sketch, context: Any, interval: float) -> None:
        now = self._perf_counter()
        draw_pending = context.state.looping or context.state.redraw_requested
        if draw_pending and now >= self._next_frame_time:
            drew_frame = self._draw_and_present(sketch)
            if drew_frame:
                self._frames_drawn += 1
            self._debug_interactive_tick("interactive draw tick", context, drew_frame)
            self._advance_next_frame_time(now, interval)
        elif not draw_pending:
            self._debug_interactive_idle(context)
        delay = self._interactive_sleep_delay(draw_pending, interval)
        if delay > 0:
            self._sleep(delay)

    def _interactive_sleep_delay(self, draw_pending: bool, interval: float) -> float:
        if draw_pending:
            return max(0.0, min(self._next_frame_time - self._perf_counter(), interval))
        return min(interval, 1.0 / 60.0)

    def _wake_for_pending_draw(self, context: Any, *, was_looping: bool) -> None:
        if context.state.redraw_requested or (context.state.looping and not was_looping):
            self._next_frame_time = self._perf_counter()

    def _debug_interactive_tick(self, label: str, context: Any, drew_frame: bool) -> None:
        if not self._debug:
            return
        self._last_idle_debug_frame = None
        print(
            "[canvas-debug] "
            f"{label} drew={drew_frame} looping={context.state.looping} "
            f"redraw={context.state.redraw_requested} frame={context.state.timing.frame_count}",
            flush=True,
        )

    def _debug_interactive_idle(self, context: Any) -> None:
        if not self._debug or self._last_idle_debug_frame == context.state.timing.frame_count:
            return
        self._last_idle_debug_frame = context.state.timing.frame_count
        print(
            "[canvas-debug] interactive idle "
            f"looping={context.state.looping} redraw={context.state.redraw_requested} "
            f"frame={context.state.timing.frame_count}",
            flush=True,
        )

    def _draw_and_present(self, sketch: Sketch) -> bool:
        context = getattr(sketch, "context", None)
        before_frame_count = context.state.timing.frame_count if context is not None else None
        draw_start = self._perf_counter()
        sketch._draw_frame()
        draw_duration_ms = (self._perf_counter() - draw_start) * 1000.0
        after_frame_count = context.state.timing.frame_count if context is not None else None
        if before_frame_count is None or after_frame_count != before_frame_count:
            present_start = self._perf_counter()
            self.present()
            present_end = self._perf_counter()
            self._record_pacing_duration("draw", draw_duration_ms)
            self._record_pacing_duration("present", (present_end - present_start) * 1000.0)
            self._record_present_interval(present_end)
            return True
        return False

    def _should_close(self, canvas: object) -> bool:
        should_close = getattr(canvas, "should_close", None)
        if callable(should_close):
            return bool(should_close())
        return False

    def _next_frame_delay(self, now: float, interval: float) -> float:
        self._advance_next_frame_time(now, interval)
        return max(0.0, self._next_frame_time - now)

    def _advance_next_frame_time(self, now: float, interval: float) -> None:
        self._next_frame_time += interval
        while self._next_frame_time <= now:
            self._next_frame_time += interval

    @staticmethod
    def _sketch_context(sketch: Sketch) -> Any:
        if sketch.context is None:
            raise BackendCapabilityError("Canvas runtime requires an active SketchContext.")
        return sketch.context
