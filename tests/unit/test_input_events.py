from dataclasses import replace

import pytest

from gummysnake.api import input as environment_input
from gummysnake.api.current import activate_context
from gummysnake.backend.canvas import CanvasBackend
from gummysnake.context import SketchContext
from gummysnake.core.vector import Vector
from gummysnake.events.input_state import (
    InputState,
    KeyboardEvent,
    MouseEvent,
    TouchEvent,
    TouchPoint,
)
from gummysnake.exceptions import BackendCapabilityError
from gummysnake.plugins.registry import GLOBAL_PLUGIN_REGISTRY
from gummysnake.sketch import Sketch


class EventSketch(Sketch):
    def __init__(self):
        super().__init__()
        self.events = []

    def mouse_pressed(self, event):
        self.events.append(("mouse_pressed", event.x, event.y, event.button))

    def key_typed(self, event):
        self.events.append(("key_typed", event.key))


def make_context():
    sketch = EventSketch()
    context = SketchContext(sketch, CanvasBackend(), plugins=GLOBAL_PLUGIN_REGISTRY)
    sketch.context = context
    return sketch, context


def test_mouse_state_and_callback_dispatch():
    sketch, context = make_context()

    context.dispatch_mouse_event(
        MouseEvent(x=10, y=12, dx=3, dy=4, button="left", type="mouse_pressed")
    )

    assert context.mouse_x == 10
    assert context.mouse_y == 12
    assert context.moved_x == 3
    assert context.moved_y == 4
    assert context.mouse_is_pressed is True
    assert context.mouse_button == "left"
    assert context.mouse_inside_window is False
    assert sketch.events == [("mouse_pressed", 10, 12, "left")]

    event = MouseEvent(x=10, y=12, dx=3, dy=4, scroll_y=-1)
    assert event.position == Vector(10, 12)
    assert event.delta == Vector(3, 4)
    assert event.scroll == Vector(0, -1)

    context.dispatch_mouse_event(MouseEvent(x=11, y=13, inside_window=True))
    assert context.mouse_inside_window is True

    context.update_mouse_inside_window(False)
    assert context.mouse_inside_window is False


def test_keyboard_state_key_is_down_and_typed_callback():
    sketch, context = make_context()

    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))
    assert context.key == "a"
    assert context.key_code == 65
    assert context.key_is_pressed is True
    assert context.key_is_down(65) is True
    assert KeyboardEvent(key="a", key_code=65).matches("a")
    assert KeyboardEvent(key="a", key_code=65).matches(65)
    assert KeyboardEvent(key="Space").matches(" ")
    assert KeyboardEvent(key=" ").matches("space")

    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_released"))
    assert context.key_is_pressed is False
    assert context.key_is_down(65) is False

    context.dispatch_keyboard_event(KeyboardEvent(key="é", key_code=233, type="key_typed"))
    assert sketch.events == [("key_typed", "é")]


def test_input_state_explicit_key_and_code_mutation_methods():
    state = InputState()

    state.set_key_down(65, True)
    state.set_code_down("KeyA", True)
    assert state.key_is_down(65) is True
    assert state.code_is_down("KeyA") is True

    state.set_key_down(65, False)
    state.set_code_down("KeyA", False)
    assert state.key_is_down(65) is False
    assert state.code_is_down("KeyA") is False


def test_keyboard_physical_code_repeat_and_string_queries():
    _sketch, context = make_context()

    context.dispatch_keyboard_event(
        KeyboardEvent(key="a", key_code=65, code="KeyA", repeat=True, type="key_pressed")
    )

    assert context.code == "KeyA"
    assert context.key_is_down("KeyA") is True
    assert context.key_is_down("a") is True

    context.dispatch_keyboard_event(
        KeyboardEvent(key="a", key_code=65, code="KeyA", type="key_released")
    )
    assert context.key_is_down("KeyA") is False


def test_mouse_event_previous_window_and_double_click_data():
    _sketch, context = make_context()
    event = MouseEvent(
        x=10,
        y=12,
        previous_x=8,
        previous_y=9,
        window_x=110,
        window_y=112,
        click_count=2,
        type="mouse_double_clicked",
    )

    context.dispatch_mouse_event(event)

    assert context.pmouse_x == 8
    assert context.pmouse_y == 9
    assert event.previous_position == Vector(8, 9)
    assert event.window_position == Vector(110, 112)
    assert event.click_count == 2


def test_mouse_coordinates_are_not_clamped_by_public_api_accessors():
    _sketch, context = make_context()
    context.state.canvas.width = 100
    context.state.canvas.height = 50

    context.dispatch_mouse_event(MouseEvent(x=-12, y=80, dx=-112, dy=30, type="mouse_moved"))

    assert context.state.input.mouse_x == -12
    assert context.state.input.mouse_y == 80
    assert context.mouse_x == -12
    assert context.mouse_y == 80
    assert context.moved_x == -112
    assert context.moved_y == 30

    context.dispatch_mouse_event(
        MouseEvent(x=120, y=-10, previous_x=-12, previous_y=80, type="mouse_moved")
    )

    assert context.mouse_x == 120
    assert context.mouse_y == -10
    assert context.pmouse_x == -12
    assert context.pmouse_y == 80
    with activate_context(context):
        assert environment_input.mouse_x() == 120
        assert environment_input.mouse_y() == -10
        assert environment_input.pmouse_x() == -12
        assert environment_input.pmouse_y() == 80


def test_pointer_lock_mode_updates_context_and_backend():
    _sketch, context = make_context()
    calls: list[str] = []

    def set_pointer_lock_mode(mode: str) -> str:
        calls.append(mode)
        return mode

    context.backend.set_pointer_lock_mode = set_pointer_lock_mode  # type: ignore[method-assign]

    assert context.pointer_lock_mode() == "clamped"
    assert context.set_pointer_lock_mode("unclamped") == "unclamped"
    assert context.state.input.pointer_lock_mode == "unclamped"
    assert context.set_pointer_lock_mode("fixed") == "fixed"
    assert calls == ["unclamped", "fixed"]

    with activate_context(context):
        assert environment_input.pointer_lock_mode() == "fixed"
        assert environment_input.pointer_lock_mode("clamped") == "clamped"
    assert calls == ["unclamped", "fixed", "clamped"]


def test_pointer_lock_reports_capability_error_when_unsupported():
    _sketch, context = make_context()
    context.backend.capabilities = replace(context.backend.capabilities, pointer_lock=False)

    with pytest.raises(BackendCapabilityError, match="Pointer lock"):
        context.request_pointer_lock()


def test_pointer_lock_updates_context_state_when_supported():
    _sketch, context = make_context()
    calls: list[str] = []
    context.backend.capabilities = replace(context.backend.capabilities, pointer_lock=True)

    def request_pointer_lock() -> bool:
        calls.append("request")
        return True

    def exit_pointer_lock() -> bool:
        calls.append("exit")
        return True

    context.backend.request_pointer_lock = request_pointer_lock  # type: ignore[method-assign]
    context.backend.exit_pointer_lock = exit_pointer_lock  # type: ignore[method-assign]

    assert context.request_pointer_lock() is True
    assert context.state.input.pointer_locked is True
    assert context.exit_pointer_lock() is True
    assert context.state.input.pointer_locked is False
    assert calls == ["request", "exit"]


def test_text_input_start_stop_updates_context_state_when_supported():
    _sketch, context = make_context()
    calls: list[str] = []
    context.backend.capabilities = replace(context.backend.capabilities, keyboard=True)

    def start_text_input() -> bool:
        calls.append("start")
        return True

    def stop_text_input() -> bool:
        calls.append("stop")
        return True

    def text_input_active() -> bool:
        return context.state.input.text_input_active

    context.backend.start_text_input = start_text_input  # type: ignore[method-assign]
    context.backend.stop_text_input = stop_text_input  # type: ignore[method-assign]
    context.backend.text_input_active = text_input_active  # type: ignore[method-assign]

    assert context.start_text_input() is True
    assert context.is_text_input_active() is True
    assert context.stop_text_input() is True
    assert context.is_text_input_active() is False
    assert calls == ["start", "stop"]


def test_touch_event_updates_when_backend_declares_support():
    _sketch, context = make_context()
    context.state.input.touch_supported = True

    context.update_touch_event(TouchEvent(touches=[TouchPoint(id=1, x=2, y=3)]))
    context.update_touch_event(TouchEvent(touches=[TouchPoint(id=1, x=4, y=5)]))

    touch = context.touches[0]
    assert (touch.x, touch.y) == (4, 5)
    assert (touch.previous_x, touch.previous_y) == (2, 3)
    assert touch.position == Vector(4, 5)
    assert touch.previous_position == Vector(2, 3)
    assert touch.delta == Vector(2, 2)


def test_touch_event_reports_capability_error_when_unsupported():
    _sketch, context = make_context()
    context.state.input.touch_supported = False

    with pytest.raises(BackendCapabilityError, match="Touch input is not supported"):
        context.update_touch_event(TouchEvent(touches=[TouchPoint(id=1, x=2, y=3)]))
