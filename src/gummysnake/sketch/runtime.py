"""Sketch lifecycle runtime."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gummysnake import constants as c
from gummysnake._async import call_maybe_async, call_maybe_async_with_optional_args
from gummysnake.api.current import activate_context
from gummysnake.backend.registry import create_backend
from gummysnake.context import SketchContext
from gummysnake.ecs.runtime_views import SystemHandle
from gummysnake.ecs.systems import SystemDefinition
from gummysnake.ecs.systems import system as ecs_system
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
        self._draw_system_handle: SystemHandle | None = None

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
        self._draw_system_handle = None
        GLOBAL_PLUGIN_REGISTRY.bind_runtime(self.context, self)
        self._running = True
        try:
            with activate_context(self.context):
                self.context.plugins.dispatch_lifecycle(
                    LifecycleHookName.BEFORE_PRELOAD, self.context
                )
                call_maybe_async(self.preload)
                self.context.plugins.dispatch_lifecycle(
                    LifecycleHookName.BEFORE_SETUP, self.context
                )
                call_maybe_async(self.setup)
                self.context.ensure_canvas()
                self._ensure_draw_system_registered()
                self.context.plugins.dispatch_lifecycle(LifecycleHookName.AFTER_SETUP, self.context)
                backend_instance.run(self, max_frames=max_frames)
        finally:
            self._running = False
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
        frame_completed = False
        try:
            with activate_context(context):
                context.run_ecs_pre_draw()
                frame_completed = True
        finally:
            context.renderer.end_frame()
            context.end_frame()
        if frame_completed:
            context.state.rust.increment_frame_count()
            context.state.redraw_requested = False

    def _draw_system_definition(self) -> SystemDefinition | None:
        return ecs_system(self.draw, name="draw", group="draw")

    def _ensure_draw_system_registered(self) -> None:
        if self.context is None or self._draw_system_handle is not None:
            return
        definition = self._draw_system_definition()
        if definition is None:
            return
        self._draw_system_handle = self.context.add_system(definition)

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
        draw_system: SystemDefinition | None = None,
        event_callbacks: dict[str, Callable[..., object]] | None = None,
        headless: bool | None = None,
    ) -> None:
        super().__init__(headless=headless)
        self._preload_func = preload
        self._setup_func = setup
        self._draw_func = draw
        self._draw_system = draw_system
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

    def _draw_system_definition(self) -> SystemDefinition | None:
        if self._draw_system is not None:
            return self._draw_system
        if self._draw_func is None:
            return None
        return super()._draw_system_definition()

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
        self._preload_func: Callable[[], Any] | None = None
        self._setup_func: Callable[[], Any] | None = None
        self._draw_func: Callable[[], Any] | None = None
        self._draw_system: SystemDefinition | None = None
        self._event_callbacks: dict[str, Callable[..., Any]] = {}

    @property
    def preload_callback(self) -> Callable[[], Any] | None:
        return self._preload_func

    @property
    def setup_callback(self) -> Callable[[], Any] | None:
        return self._setup_func

    @property
    def draw_callback(self) -> Callable[[], Any] | None:
        return self._draw_func

    @property
    def draw_system(self) -> SystemDefinition | None:
        return self._draw_system

    @property
    def event_callbacks(self) -> dict[str, Callable[..., Any]]:
        return dict(self._event_callbacks)

    def preload[F: Callable[[], Any]](self, callback: F) -> F:
        self._preload_func = callback
        return callback

    def setup[F: Callable[[], Any]](self, callback: F) -> F:
        self._setup_func = callback
        return callback

    def draw[F: Callable[[], Any]](self, callback: F) -> F:
        self._draw_func = callback
        self._draw_system = ecs_system(callback, group="draw")
        return callback

    def register_draw_system(self, definition: SystemDefinition) -> None:
        self._draw_system = definition
        self._draw_func = definition.function  # compatibility for code that inspects the builder

    def on[F: Callable[..., Any]](
        self, event_name: str | c.CallbackEventName | c.TouchEventName
    ) -> Callable[[F], F]:
        normalized_event_name = _normalize_event_name(event_name)

        def decorator(callback: F) -> F:
            self._event_callbacks[normalized_event_name] = callback
            return callback

        return decorator

    def __getattr__[F: Callable[..., Any]](self, name: str) -> Callable[[F], F]:
        if name in EVENT_CALLBACK_NAMES:
            return self.on(name)
        raise AttributeError(name)

    def to_sketch(self, *, headless: bool | None = None) -> FunctionSketch:
        return FunctionSketch(
            preload=self._preload_func,
            setup=self._setup_func,
            draw=self._draw_func,
            draw_system=self._draw_system,
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
