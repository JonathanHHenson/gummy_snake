"""Sketch lifecycle runtime."""

from __future__ import annotations

from collections.abc import Callable

from gummysnake import constants as c
from gummysnake._async import call_maybe_async, call_maybe_async_with_optional_args
from gummysnake.api.current import activate_context
from gummysnake.backend.registry import create_backend
from gummysnake.context import SketchContext
from gummysnake.plugins.base import LifecycleHookName
from gummysnake.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from gummysnake.sketch.facade import SketchFacadeMixin

EVENT_CALLBACK_NAMES = tuple(event.value for event in c.CallbackEventName)


class Sketch(SketchFacadeMixin):
    """Base class for object-oriented Gummy Snake sketches."""

    def __init__(self, *, headless: bool | None = None) -> None:
        self.headless = headless
        self.context: SketchContext | None = None
        self._running = False

    def preload(self) -> object:
        pass

    def setup(self) -> object:
        pass

    def draw(self) -> object:
        pass

    def run(
        self,
        *,
        headless: bool | None = None,
        max_frames: int | None = None,
    ) -> SketchContext:
        runtime_headless = self.headless if headless is None else headless
        backend_instance = create_backend(headless=runtime_headless)
        self.context = SketchContext(self, backend_instance, plugins=GLOBAL_PLUGIN_REGISTRY)
        GLOBAL_PLUGIN_REGISTRY.bind_runtime(self.context, self)
        self._running = True
        with activate_context(self.context):
            self.context.plugins.dispatch_lifecycle(LifecycleHookName.BEFORE_PRELOAD, self.context)
            call_maybe_async(self.preload)
            self.context.plugins.dispatch_lifecycle(LifecycleHookName.BEFORE_SETUP, self.context)
            call_maybe_async(self.setup)
            self.context.ensure_canvas()
            self.context.plugins.dispatch_lifecycle(LifecycleHookName.AFTER_SETUP, self.context)
            backend_instance.run(self, max_frames=max_frames)
        return self.context

    def stop(self) -> None:
        self._running = False
        if self.context is not None:
            self.context.backend.stop()

    def _draw_frame(self) -> None:
        if not self._running or self.context is None:
            return
        context = self.context
        should_draw = context.state.looping or context.state.redraw_requested
        if not should_draw:
            return
        context.state.timing.begin_frame()
        context.begin_frame()
        context.renderer.begin_frame()
        with activate_context(context):
            context.plugins.dispatch_lifecycle(LifecycleHookName.BEFORE_DRAW, context)
            call_maybe_async(self.draw)
            context.plugins.dispatch_lifecycle(LifecycleHookName.AFTER_DRAW, context)
        context.renderer.end_frame()
        context.end_frame()
        context.state.timing.frame_count += 1
        context.state.redraw_requested = False

    def _dispatch_callback(self, name: str, event: object) -> None:
        callback = getattr(self, name, None)
        if callable(callback):
            call_maybe_async_with_optional_args(callback, event)


class FunctionSketch(Sketch):
    """Sketch wrapper for module-level/global-mode functions."""

    def __init__(
        self,
        *,
        preload: Callable[[], object] | None = None,
        setup: Callable[[], object] | None = None,
        draw: Callable[[], object] | None = None,
        event_callbacks: dict[str, Callable[..., object]] | None = None,
        headless: bool | None = None,
    ) -> None:
        super().__init__(headless=headless)
        self._preload_func = preload
        self._setup_func = setup
        self._draw_func = draw
        self._event_callbacks = event_callbacks or {}

    def preload(self) -> object:
        if self._preload_func is not None:
            return self._preload_func()
        return None

    def setup(self) -> object:
        if self._setup_func is not None:
            return self._setup_func()
        return None

    def draw(self) -> object:
        if self._draw_func is not None:
            return self._draw_func()
        return None

    def _dispatch_callback(self, name: str, event: object) -> None:
        callback = self._event_callbacks.get(name)
        if callback is None:
            super()._dispatch_callback(name, event)
            return
        call_maybe_async_with_optional_args(callback, event)


class SketchBuilder:
    """Decorator-friendly sketch callback registry."""

    def __init__(self, *, headless: bool | None = None) -> None:
        self.headless = headless
        self._preload_func: Callable[[], object] | None = None
        self._setup_func: Callable[[], object] | None = None
        self._draw_func: Callable[[], object] | None = None
        self._event_callbacks: dict[str, Callable[..., object]] = {}

    @property
    def preload_callback(self) -> Callable[[], object] | None:
        return self._preload_func

    @property
    def setup_callback(self) -> Callable[[], object] | None:
        return self._setup_func

    @property
    def draw_callback(self) -> Callable[[], object] | None:
        return self._draw_func

    @property
    def event_callbacks(self) -> dict[str, Callable[..., object]]:
        return dict(self._event_callbacks)

    def preload(self, callback: Callable[[], object]) -> Callable[[], object]:
        self._preload_func = callback
        return callback

    def setup(self, callback: Callable[[], object]) -> Callable[[], object]:
        self._setup_func = callback
        return callback

    def draw(self, callback: Callable[[], object]) -> Callable[[], object]:
        self._draw_func = callback
        return callback

    def on(
        self, event_name: str | c.CallbackEventName | c.TouchEventName
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        normalized_event_name = _normalize_event_name(event_name)

        def decorator(callback: Callable[..., object]) -> Callable[..., object]:
            self._event_callbacks[normalized_event_name] = callback
            return callback

        return decorator

    def __getattr__(self, name: str) -> Callable[[Callable[..., object]], Callable[..., object]]:
        if name in EVENT_CALLBACK_NAMES:
            return self.on(name)
        raise AttributeError(name)

    def to_sketch(self, *, headless: bool | None = None) -> FunctionSketch:
        return FunctionSketch(
            preload=self._preload_func,
            setup=self._setup_func,
            draw=self._draw_func,
            event_callbacks=self.event_callbacks,
            headless=self.headless if headless is None else headless,
        )

    def run(
        self,
        *,
        headless: bool | None = None,
        max_frames: int | None = None,
    ) -> SketchContext:
        return self.to_sketch(headless=headless).run(max_frames=max_frames)


def _normalize_event_name(event_name: str | c.CallbackEventName | c.TouchEventName) -> str:
    normalized = (
        event_name.value
        if isinstance(event_name, c.CallbackEventName | c.TouchEventName)
        else str(event_name)
    )
    if normalized not in EVENT_CALLBACK_NAMES:
        raise ValueError(f"Unknown Gummy Snake event callback {event_name!r}.")
    return normalized
