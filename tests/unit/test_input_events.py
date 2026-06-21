import pytest

from gummysnake.backend.canvas import CanvasBackend
from gummysnake.context import SketchContext
from gummysnake.core.vector import Vector
from gummysnake.events.input_state import KeyboardEvent, MouseEvent, TouchEvent, TouchPoint
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
    assert sketch.events == [("mouse_pressed", 10, 12, "left")]

    event = MouseEvent(x=10, y=12, dx=3, dy=4, scroll_y=-1)
    assert event.position == Vector(10, 12)
    assert event.delta == Vector(3, 4)
    assert event.scroll == Vector(0, -1)


def test_keyboard_state_key_is_down_and_typed_callback():
    sketch, context = make_context()

    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))
    assert context.key == "a"
    assert context.key_code == 65
    assert context.key_is_pressed is True
    assert context.key_is_down(65) is True
    assert KeyboardEvent(key="a", key_code=65).matches("a")
    assert KeyboardEvent(key="a", key_code=65).matches(65)

    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_released"))
    assert context.key_is_pressed is False
    assert context.key_is_down(65) is False

    context.dispatch_keyboard_event(KeyboardEvent(key="é", key_code=233, type="key_typed"))
    assert sketch.events == [("key_typed", "é")]


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
