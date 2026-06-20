from typing import Any, cast

import pytest

import p5
from p5.events.input_state import KeyboardEvent, MouseEvent
from p5.plugins import Plugin, clear_plugins, install_plugin, list_plugins, uninstall_plugin
from p5.sketch import Sketch


@pytest.fixture(autouse=True)
def _clear_plugin_registry():
    clear_plugins()
    yield
    clear_plugins()


class HookSketch(Sketch):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def preload(self) -> None:
        self.events.append("preload")
        assert cast(Any, p5).mark_frame("preload") == 0

    def setup(self) -> None:
        self.events.append("setup")
        self.create_canvas(16, 12)
        assert cast(Any, self).mark_frame("setup") == 0

    def draw(self) -> None:
        self.events.append(f"draw:{self.frame_count}")
        self.background(240)
        self.no_stroke()
        self.fill(255, 0, 0)
        self.circle(8, 6, 6)
        assert cast(Any, p5).mark_frame(f"draw:{self.frame_count}") == self.frame_count


class RecorderPlugin(Plugin):
    name = "recorder"
    priority = 10

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def install(self, registry) -> None:
        self.events.append("install")
        registry.expose_api("mark_frame", self.mark_frame)

    def uninstall(self, registry) -> None:
        del registry
        self.events.append("uninstall")

    def mark_frame(self, context, label: str) -> int:
        self.events.append(f"api:{label}:{context.frame_count}")
        return context.frame_count

    def before_preload(self, context) -> None:
        del context
        self.events.append("before_preload")

    def before_setup(self, context) -> None:
        del context
        self.events.append("before_setup")

    def after_setup(self, context) -> None:
        self.events.append(f"after_setup:{context.width}x{context.height}")

    def before_draw(self, context) -> None:
        self.events.append(f"before_draw:{context.frame_count}")

    def after_draw(self, context) -> None:
        self.events.append(f"after_draw:{context.frame_count}")


class EventPlugin(Plugin):
    name = "event-recorder"

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def on_mouse_event(self, context, event: MouseEvent) -> None:
        del context
        self.events.append(f"plugin:{event.type}")

    def on_keyboard_event(self, context, event: KeyboardEvent) -> None:
        del context
        self.events.append(f"plugin:{event.type}")


class OrderedPlugin(Plugin):
    def __init__(self, name: str, priority: int, events: list[str]) -> None:
        self.name = name
        self.priority = priority
        self.events = events

    def before_draw(self, context) -> None:
        del context
        self.events.append(self.name)


def test_plugin_hooks_api_extension_and_cleanup():
    events: list[str] = []
    install_plugin(RecorderPlugin(events))
    sketch = HookSketch(events)

    context = sketch.run(max_frames=2)

    assert context.frame_count == 2
    assert list_plugins() == ("recorder",)
    assert events == [
        "install",
        "before_preload",
        "preload",
        "api:preload:0",
        "before_setup",
        "setup",
        "api:setup:0",
        "after_setup:16x12",
        "before_draw:0",
        "draw:0",
        "api:draw:0:0",
        "after_draw:0",
        "before_draw:1",
        "draw:1",
        "api:draw:1:1",
        "after_draw:1",
    ]

    uninstall_plugin("recorder")
    assert not hasattr(p5, "mark_frame")
    assert events[-1] == "uninstall"


def test_plugin_ordering_is_deterministic_by_priority_then_install_order():
    events: list[str] = []
    install_plugin(OrderedPlugin("first", 5, events))
    install_plugin(OrderedPlugin("second", 5, events))
    install_plugin(OrderedPlugin("third", 20, events))

    class DrawOnceSketch(Sketch):
        def __init__(self) -> None:
            super().__init__()

        def setup(self) -> None:
            self.create_canvas(4, 4)

        def draw(self) -> None:
            self.background(0)

    DrawOnceSketch().run(max_frames=1)

    assert events == ["first", "second", "third"]


def test_plugins_receive_events_before_sketch_callbacks():
    events: list[str] = []
    install_plugin(EventPlugin(events))

    class EventSketch(Sketch):
        def __init__(self) -> None:
            super().__init__()

        def setup(self) -> None:
            self.create_canvas(8, 8)

        def mouse_pressed(self, event) -> None:
            events.append(f"sketch:{event.type}")

        def key_pressed(self, event) -> None:
            events.append(f"sketch:{event.type}")

    sketch = EventSketch()
    context = sketch.run(max_frames=0)

    context.dispatch_mouse_event(MouseEvent(x=3, y=4, button="left", type="mouse_pressed"))
    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))

    assert events == [
        "plugin:mouse_pressed",
        "sketch:mouse_pressed",
        "plugin:key_pressed",
        "sketch:key_pressed",
    ]
