"""Sketch lifecycle runtime."""

from __future__ import annotations

from collections.abc import Buffer, Callable, Sequence
from contextlib import contextmanager
from typing import Any

from gummysnake import constants as c
from gummysnake._async import call_maybe_async, call_maybe_async_with_optional_args
from gummysnake.api.current import activate_context
from gummysnake.backends.registry import create_backend
from gummysnake.context import SketchContext
from gummysnake.plugins.base import LifecycleHookName
from gummysnake.plugins.registry import GLOBAL_PLUGIN_REGISTRY

EVENT_CALLBACK_NAMES = tuple(event.value for event in c.CallbackEventName)


class Sketch:
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

    # Lifecycle delegates
    def no_loop(self) -> None:
        self._ctx.no_loop()

    def loop(self) -> None:
        self._ctx.loop()

    def redraw(self) -> None:
        self._ctx.redraw()

    def is_looping(self) -> bool:
        return self._ctx.is_looping()

    # Canvas / style / drawing delegates
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

    def fast(self):
        return self._ctx.fast()

    def enable_performance_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        self._ctx.enable_performance_diagnostics(enabled, reset=reset)

    def reset_performance_diagnostics(self) -> None:
        self._ctx.reset_performance_diagnostics()

    def performance_diagnostics(self) -> dict[str, object]:
        return self._ctx.performance_diagnostics()

    def renderer_performance_counters(self) -> dict[str, object]:
        return self._ctx.renderer_performance_counters()

    def reset_renderer_performance_counters(self) -> None:
        self._ctx.reset_renderer_performance_counters()

    def enable_frame_pacing_diagnostics(self, enabled: bool = True, *, reset: bool = True) -> None:
        self._ctx.enable_frame_pacing_diagnostics(enabled, reset=reset)

    def frame_pacing_diagnostics(self) -> dict[str, object]:
        return self._ctx.frame_pacing_diagnostics()

    def reset_frame_pacing_diagnostics(self) -> None:
        self._ctx.reset_frame_pacing_diagnostics()

    def background(self, *args: object) -> None:
        self._ctx.background(*args)

    def clear(self) -> None:
        self._ctx.clear()

    def fill(self, *args: object) -> None:
        self._ctx.fill(*args)

    def no_fill(self) -> None:
        self._ctx.no_fill()

    def stroke(self, *args: object) -> None:
        self._ctx.stroke(*args)

    def no_stroke(self) -> None:
        self._ctx.no_stroke()

    def stroke_weight(self, weight: float) -> None:
        self._ctx.stroke_weight(weight)

    def point(self, x: float, y: float) -> None:
        self._ctx.point(x, y)

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self._ctx.line(x1, y1, x2, y2)

    def rect(self, x: float, y: float, width: float, height: float | None = None) -> None:
        self._ctx.rect(x, y, width, height)

    def square(self, x: float, y: float, size: float) -> None:
        self._ctx.square(x, y, size)

    def ellipse(self, x: float, y: float, width: float, height: float | None = None) -> None:
        self._ctx.ellipse(x, y, width, height)

    def circle(self, x: float, y: float, diameter: float) -> None:
        self._ctx.circle(x, y, diameter)

    def triangle(self, *coords: float) -> None:
        self._ctx.triangle(*coords)

    def quad(self, *coords: float) -> None:
        self._ctx.quad(*coords)

    def arc(self, *args: Any) -> None:
        self._ctx.arc(*args)

    def create_camera(self, *args: object):
        return self._ctx.create_camera(*args)

    def camera(self, *args: object):
        return self._ctx.camera(*args)

    def perspective(self, *args: object):
        return self._ctx.perspective(*args)

    def ortho(self, *args: object):
        return self._ctx.ortho(*args)

    def orbit_control(self, *args: object):
        return self._ctx.orbit_control(*args)

    def ambient_light(self, *args: object) -> None:
        self._ctx.ambient_light(*args)

    def directional_light(self, *args: object) -> None:
        self._ctx.directional_light(*args)

    def point_light(self, *args: object) -> None:
        self._ctx.point_light(*args)

    def normal_material(self) -> None:
        self._ctx.normal_material()

    def ambient_material(self, *args: object) -> None:
        self._ctx.ambient_material(*args)

    def specular_material(self, *args: object) -> None:
        self._ctx.specular_material(*args)

    def shininess(self, value: float) -> None:
        self._ctx.shininess(value)

    def texture(self, image) -> None:
        self._ctx.texture(image)

    def plane(self, width: float, height: float | None = None) -> None:
        self._ctx.plane(width, height)

    def box(self, width: float, height: float | None = None, depth: float | None = None) -> None:
        self._ctx.box(width, height, depth)

    def sphere(self, radius: float, detail_x: int = 24, detail_y: int = 16) -> None:
        self._ctx.sphere(radius, detail_x, detail_y)

    def model(self, shape: object) -> None:
        self._ctx.model(shape)

    def load_shader(self, vertex_path: str, fragment_path: str):
        return self._ctx.load_shader(vertex_path, fragment_path)

    def create_shader(self, vertex_source: str, fragment_source: str):
        return self._ctx.create_shader(vertex_source, fragment_source)

    def shader(self, shader_program) -> None:
        self._ctx.shader(shader_program)

    def reset_shader(self) -> None:
        self._ctx.reset_shader()

    def push(self) -> None:
        self._ctx.push()

    def pop(self) -> None:
        self._ctx.pop()

    @contextmanager
    def pushed(self):
        self.push()
        try:
            yield
        finally:
            self.pop()

    def translate(self, x: float, y: float) -> None:
        self._ctx.translate(x, y)

    def rotate(self, angle: float) -> None:
        self._ctx.rotate(angle)

    def scale(self, x: float, y: float | None = None) -> None:
        self._ctx.scale(x, y)

    @property
    def width(self) -> int:
        return self._ctx.width

    @property
    def height(self) -> int:
        return self._ctx.height

    @property
    def frame_count(self) -> int:
        return self._ctx.frame_count

    def load_pixels(self) -> list[int]:
        return self._ctx.load_pixels()

    def load_pixel_bytes(self) -> bytes:
        return self._ctx.load_pixel_bytes()

    def update_pixels(self, pixels: Sequence[int] | Buffer | None = None) -> None:
        self._ctx.update_pixels(pixels)

    def save_canvas(self, *args: Any, **kwargs: Any):
        return self._ctx.save_canvas(*args, **kwargs)

    def blend_mode(self, mode: c.BlendMode) -> None:
        self._ctx.blend_mode(mode)

    def blend(self, *args: object) -> None:
        self._ctx.blend(*args)

    def erase(self) -> None:
        self._ctx.erase()

    def no_erase(self) -> None:
        self._ctx.no_erase()

    @property
    def mouse_x(self) -> float:
        return self._ctx.mouse_x

    @property
    def mouse_y(self) -> float:
        return self._ctx.mouse_y

    @property
    def pmouse_x(self) -> float:
        return self._ctx.pmouse_x

    @property
    def pmouse_y(self) -> float:
        return self._ctx.pmouse_y

    @property
    def mouse_is_pressed(self) -> bool:
        return self._ctx.mouse_is_pressed

    @property
    def key(self) -> str | None:
        return self._ctx.key

    @property
    def key_code(self) -> int | None:
        return self._ctx.key_code

    @property
    def key_is_pressed(self) -> bool:
        return self._ctx.key_is_pressed

    def key_is_down(self, key_code: int) -> bool:
        return self._ctx.key_is_down(key_code)

    @property
    def _ctx(self) -> SketchContext:
        if self.context is None:
            raise RuntimeError("Sketch context is not available until run() starts.")
        return self.context


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
