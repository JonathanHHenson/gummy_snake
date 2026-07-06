"""Global-mode sketch construction and lifecycle decorators."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import cast

from gummysnake import constants as c
from gummysnake.context import SketchContext
from gummysnake.sketch import EVENT_CALLBACK_NAMES, FunctionSketch, SketchBuilder

type LifecycleCallback = Callable[[], object]
type EventCallback = Callable[..., object]

_DECORATED_SKETCHES: dict[str, SketchBuilder] = {}


def sketch(*, headless: bool | None = None) -> SketchBuilder:
    """Create a decorator-friendly sketch builder.

    Args:
        headless: Set to ``True`` for offscreen/bounded runs, ``False`` for an
            interactive window, or omit to use the normal runtime default.

    Returns:
        A ``SketchBuilder`` that can register ``setup()``, ``draw()``, and events.
    """

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


def preload[F: LifecycleCallback](callback: F) -> F:
    """Register a function that runs before setup for loading assets.

    Args:
        callback: Function called once before ``setup()``. It may be synchronous
            or asynchronous.

    Returns:
        The original callback so the decorator does not change the function.
    """

    return _module_builder(_caller_module_name()).preload(callback)


def setup[F: LifecycleCallback](callback: F) -> F:
    """Register a function that initializes the sketch.

    Args:
        callback: Function called once after preload and before the first frame.
            It may be synchronous or asynchronous.

    Returns:
        The original callback so the decorator does not change the function.
    """

    return _module_builder(_caller_module_name()).setup(callback)


def draw[F: LifecycleCallback](callback: F) -> F:
    """Register a function that draws each frame.

    Args:
        callback: Function called for each scheduled frame. It may be synchronous
            or asynchronous.

    Returns:
        The original callback so the decorator does not change the function.
    """

    return _module_builder(_caller_module_name()).draw(callback)


def on[F: EventCallback](
    event_name: str | c.CallbackEventName | c.TouchEventName,
) -> Callable[[F], F]:
    """Register an event callback by name.

    Args:
        event_name: Event name such as ``"mouse_pressed"`` or an enum-backed
            event constant.

    Returns:
        A decorator that stores the callback and returns it unchanged.
    """

    return _module_builder(_caller_module_name()).on(event_name)


def run(
    *,
    preload: LifecycleCallback | None = None,
    setup: LifecycleCallback | None = None,
    draw: LifecycleCallback | None = None,
    mouse_moved: EventCallback | None = None,
    mouse_dragged: EventCallback | None = None,
    mouse_pressed: EventCallback | None = None,
    mouse_released: EventCallback | None = None,
    mouse_clicked: EventCallback | None = None,
    mouse_double_clicked: EventCallback | None = None,
    mouse_wheel: EventCallback | None = None,
    key_pressed: EventCallback | None = None,
    key_released: EventCallback | None = None,
    key_typed: EventCallback | None = None,
    touch_started: EventCallback | None = None,
    touch_moved: EventCallback | None = None,
    touch_ended: EventCallback | None = None,
    touch_cancelled: EventCallback | None = None,
    device_moved: EventCallback | None = None,
    device_turned: EventCallback | None = None,
    device_shaken: EventCallback | None = None,
    headless: bool | None = None,
    max_frames: int | None = None,
) -> SketchContext:
    """Build and run a sketch from callbacks in global mode.

    Args:
        preload: Optional asset-loading callback called before setup.
        setup: Optional initialization callback called once.
        draw: Optional per-frame drawing callback.
        mouse_moved: Optional callback for mouse movement events.
        mouse_dragged: Optional callback for drag events while a mouse button is down.
        mouse_pressed: Optional callback for mouse button press events.
        mouse_released: Optional callback for mouse button release events.
        mouse_clicked: Optional callback for mouse click events.
        mouse_double_clicked: Optional callback for double-click events.
        mouse_wheel: Optional callback for mouse wheel events.
        key_pressed: Optional callback for key press events.
        key_released: Optional callback for key release events.
        key_typed: Optional callback for typed text events.
        touch_started: Optional callback for touch-start events.
        touch_moved: Optional callback for touch-move events.
        touch_ended: Optional callback for touch-end events.
        touch_cancelled: Optional callback for touch-cancel events.
        device_moved: Optional callback for device movement events.
        device_turned: Optional callback for device turn events.
        device_shaken: Optional callback for device shake events.
        headless: Set to ``True`` for offscreen/bounded runs, ``False`` for an
            interactive window, or omit to use the default runtime choice.
        max_frames: Optional maximum frame count for bounded runs.

    Returns:
        The ``SketchContext`` used by the completed or running sketch.
    """

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
        "device_moved": device_moved,
        "device_turned": device_turned,
        "device_shaken": device_shaken,
    }
    event_callbacks: dict[str, EventCallback] = {}
    decorated_event_callbacks = decorated.event_callbacks if decorated is not None else {}
    for name in EVENT_CALLBACK_NAMES:
        callback = (
            explicit_event_callbacks[name]
            or decorated_event_callbacks.get(name)
            or caller_globals.get(name)
        )
        if callable(callback):
            event_callbacks[name] = cast(EventCallback, callback)
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


__all__ = [
    "sketch",
    "preload",
    "setup",
    "draw",
    "on",
    "run",
]
