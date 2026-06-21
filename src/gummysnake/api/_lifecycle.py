"""Global-mode sketch construction and lifecycle decorators."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast

from gummysnake import constants as c
from gummysnake.context import SketchContext
from gummysnake.sketch import EVENT_CALLBACK_NAMES, FunctionSketch, SketchBuilder

_DECORATED_SKETCHES: dict[str, SketchBuilder] = {}


def sketch(*, headless: bool | None = None) -> SketchBuilder:
    return SketchBuilder(headless=headless)


def _module_builder(module_name: str, *, headless: bool | None = None) -> SketchBuilder:
    builder = _DECORATED_SKETCHES.get(module_name)
    if builder is None:
        builder = SketchBuilder(headless=headless)
        _DECORATED_SKETCHES[module_name] = builder
    elif headless is not None:
        builder.headless = headless
    return builder


def _caller_module_name() -> str:
    current_frame = inspect.currentframe()
    caller_frame = current_frame.f_back.f_back if current_frame and current_frame.f_back else None
    caller_globals = caller_frame.f_globals if caller_frame is not None else {}
    return str(caller_globals.get("__name__", "__main__"))


def preload(callback: Callable[[], object]) -> Callable[[], object]:
    return _module_builder(_caller_module_name()).preload(callback)


def setup(callback: Callable[[], object]) -> Callable[[], object]:
    return _module_builder(_caller_module_name()).setup(callback)


def draw(callback: Callable[[], object]) -> Callable[[], object]:
    return _module_builder(_caller_module_name()).draw(callback)


def on(
    event_name: str | c.CallbackEventName | c.TouchEventName,
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    return _module_builder(_caller_module_name()).on(event_name)


def run(
    *,
    preload: Callable[[], object] | None = None,
    setup: Callable[[], object] | None = None,
    draw: Callable[[], object] | None = None,
    mouse_moved: Callable[..., None] | None = None,
    mouse_dragged: Callable[..., None] | None = None,
    mouse_pressed: Callable[..., None] | None = None,
    mouse_released: Callable[..., None] | None = None,
    mouse_clicked: Callable[..., None] | None = None,
    mouse_double_clicked: Callable[..., None] | None = None,
    mouse_wheel: Callable[..., None] | None = None,
    key_pressed: Callable[..., None] | None = None,
    key_released: Callable[..., None] | None = None,
    key_typed: Callable[..., None] | None = None,
    touch_started: Callable[..., None] | None = None,
    touch_moved: Callable[..., None] | None = None,
    touch_ended: Callable[..., None] | None = None,
    touch_cancelled: Callable[..., None] | None = None,
    headless: bool | None = None,
    max_frames: int | None = None,
) -> SketchContext:
    current_frame = inspect.currentframe()
    caller_frame = current_frame.f_back if current_frame is not None else None
    caller_globals = caller_frame.f_globals if caller_frame is not None else {}
    decorated = _DECORATED_SKETCHES.get(str(caller_globals.get("__name__", "__main__")))
    explicit_event_callbacks = {
        "mouse_moved": mouse_moved,
        "mouse_dragged": mouse_dragged,
        "mouse_pressed": mouse_pressed,
        "mouse_released": mouse_released,
        "mouse_clicked": mouse_clicked,
        "mouse_double_clicked": mouse_double_clicked,
        "mouse_wheel": mouse_wheel,
        "key_pressed": key_pressed,
        "key_released": key_released,
        "key_typed": key_typed,
        "touch_started": touch_started,
        "touch_moved": touch_moved,
        "touch_ended": touch_ended,
        "touch_cancelled": touch_cancelled,
    }
    event_callbacks: dict[str, Callable[..., object]] = {}
    decorated_event_callbacks = decorated.event_callbacks if decorated is not None else {}
    for name in EVENT_CALLBACK_NAMES:
        callback = (
            explicit_event_callbacks[name]
            or decorated_event_callbacks.get(name)
            or caller_globals.get(name)
        )
        if callable(callback):
            event_callbacks[name] = cast(Callable[..., None], callback)
    sketch = FunctionSketch(
        preload=preload
        or (decorated.preload_callback if decorated is not None else None)
        or caller_globals.get("preload"),
        setup=setup
        or (decorated.setup_callback if decorated is not None else None)
        or caller_globals.get("setup"),
        draw=draw
        or (decorated.draw_callback if decorated is not None else None)
        or caller_globals.get("draw"),
        event_callbacks=event_callbacks,
        headless=headless,
    )
    return sketch.run(max_frames=max_frames)
