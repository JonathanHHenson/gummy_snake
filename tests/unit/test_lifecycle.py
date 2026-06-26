import pytest

from gummysnake import Image, Sketch
from gummysnake.core.input_events import KeyboardEvent
from gummysnake.plugins.base import LifecycleHookName


class CounterSketch(Sketch):
    def __init__(self):
        super().__init__()
        self.calls = []

    def preload(self):
        self.calls.append("preload")

    def setup(self):
        self.calls.append("setup")
        self.create_canvas(20, 20)

    def draw(self):
        self.calls.append("draw")
        self.background(255)


def test_sketch_lifecycle_runs_in_order():
    sketch = CounterSketch()
    context = sketch.run(max_frames=3)

    assert sketch.calls == ["preload", "setup", "draw", "draw", "draw"]
    assert context.width == 20
    assert context.height == 20
    assert context.frame_count == 3
    assert sketch._running is False
    assert context.backend._running is False


def test_no_loop_prevents_draw_frames():
    class NoLoopSketch(Sketch):
        def __init__(self):
            super().__init__()

        def setup(self):
            self.create_canvas(10, 10)
            self.no_loop()

        def draw(self):
            raise AssertionError("draw should not run after no_loop in setup")

    context = NoLoopSketch().run(max_frames=2)
    assert context.frame_count == 0


def test_no_loop_called_from_draw_prevents_later_draw_frames():
    class StopAfterFirstDrawSketch(Sketch):
        def __init__(self):
            super().__init__()
            self.draws = 0

        def setup(self):
            self.create_canvas(10, 10)

        def draw(self):
            self.draws += 1
            self.no_loop()

    sketch = StopAfterFirstDrawSketch()
    context = sketch.run(max_frames=4)

    assert sketch.draws == 1
    assert context.frame_count == 1


def test_redraw_draws_one_frame_while_looping_is_disabled():
    class RedrawSketch(Sketch):
        def __init__(self):
            super().__init__()
            self.draws = 0

        def setup(self):
            self.create_canvas(10, 10)
            self.no_loop()
            self.redraw()

        def draw(self):
            self.draws += 1

    sketch = RedrawSketch()
    context = sketch.run(max_frames=4)

    assert sketch.draws == 1
    assert context.frame_count == 1
    assert context.is_looping() is False


def test_async_sketch_lifecycle_callbacks_are_awaited():
    class AsyncSketch(Sketch):
        def __init__(self):
            super().__init__()
            self.calls = []

        async def preload(self):
            self.calls.append("preload")

        async def setup(self):
            self.calls.append("setup")
            self.create_canvas(10, 10)

        async def draw(self):
            self.calls.append(f"draw:{self.frame_count}")
            if self.frame_count == 1:
                self.no_loop()

    sketch = AsyncSketch()
    context = sketch.run(max_frames=4)

    assert sketch.calls == ["preload", "setup", "draw:0", "draw:1"]
    assert context.frame_count == 2


def test_object_facade_forwards_grouped_media_style_transform_methods():
    class FacadeSketch(Sketch):
        def __init__(self):
            super().__init__()
            self.results: tuple[bool, float, float] | None = None

        def setup(self):
            self.create_canvas(12, 12)
            self.frame_rate(120)

        def draw(self):
            sprite = Image(1, 1, bytes([255, 255, 255, 255]))
            with self.style(fill=(255, 0, 0), stroke=None):
                self.rect(0, 0, 4, 4)
            with self.transform(translate=(1, 1), scale=1):
                self.line(0, 0, 4, 4)
            self.image(sprite, 2, 2, 1, 1)
            self.text_size(14)
            self.text("hi", 1, 10)
            self.results = (self.text_width("hi") > 0, self.frame_rate(), self.delta_time)
            self.no_loop()

    sketch = FacadeSketch()
    context = sketch.run(max_frames=3)

    assert sketch.results is not None
    assert sketch.results[0] is True
    assert sketch.results[1] == 120
    assert sketch.results[2] >= 0
    assert context.frame_count == 1


def test_async_event_callback_is_awaited():
    class AsyncEventSketch(Sketch):
        def __init__(self):
            super().__init__()
            self.events = []

        def setup(self):
            self.create_canvas(10, 10)

        async def key_pressed(self, event):
            self.events.append((event.key, event.key_code))

    sketch = AsyncEventSketch()
    context = sketch.run(max_frames=0)

    context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))

    assert sketch.events == [("a", 65)]


def test_draw_exception_runs_frame_cleanup_without_incrementing_frame_count():
    class FailingDrawSketch(Sketch):
        def __init__(self):
            super().__init__()
            self.cleanup: list[str] = []

        def setup(self):
            self.create_canvas(10, 10)
            context = self.context
            assert context is not None
            original_renderer_end_frame = context.renderer.end_frame
            original_context_end_frame = context.end_frame

            def renderer_end_frame():
                self.cleanup.append("renderer_end_frame")
                original_renderer_end_frame()

            def context_end_frame():
                self.cleanup.append("context_end_frame")
                original_context_end_frame()

            context.renderer.end_frame = renderer_end_frame
            context.end_frame = context_end_frame

        def draw(self):
            self.cleanup.append("draw")
            raise RuntimeError("draw failed")

    sketch = FailingDrawSketch()

    with pytest.raises(RuntimeError, match="draw failed"):
        sketch.run(max_frames=1)

    assert sketch.cleanup == ["draw", "renderer_end_frame", "context_end_frame"]
    assert sketch.context is not None
    assert sketch.context.frame_count == 0
    assert sketch._running is False
    assert sketch.context.backend._running is False


def test_after_draw_plugin_exception_runs_frame_cleanup_without_incrementing_frame_count(
    monkeypatch,
):
    class FailingPluginHookSketch(Sketch):
        def __init__(self):
            super().__init__()
            self.cleanup: list[str] = []

        def setup(self):
            self.create_canvas(10, 10)
            context = self.context
            assert context is not None
            original_dispatch_lifecycle = context.plugins.dispatch_lifecycle
            original_renderer_end_frame = context.renderer.end_frame
            original_context_end_frame = context.end_frame

            def dispatch_lifecycle(hook_name, context):
                if hook_name is LifecycleHookName.AFTER_DRAW:
                    self.cleanup.append("after_draw_hook")
                    raise RuntimeError("plugin failed")
                original_dispatch_lifecycle(hook_name, context)

            def renderer_end_frame():
                self.cleanup.append("renderer_end_frame")
                original_renderer_end_frame()

            def context_end_frame():
                self.cleanup.append("context_end_frame")
                original_context_end_frame()

            monkeypatch.setattr(context.plugins, "dispatch_lifecycle", dispatch_lifecycle)
            context.renderer.end_frame = renderer_end_frame
            context.end_frame = context_end_frame

        def draw(self):
            self.cleanup.append("draw")

    sketch = FailingPluginHookSketch()

    with pytest.raises(RuntimeError, match="plugin failed"):
        sketch.run(max_frames=1)

    assert sketch.cleanup == [
        "draw",
        "after_draw_hook",
        "renderer_end_frame",
        "context_end_frame",
    ]
    assert sketch.context is not None
    assert sketch.context.frame_count == 0
    assert sketch._running is False
    assert sketch.context.backend._running is False


def test_async_event_callback_type_error_is_not_retried_without_event():
    class FailingEventSketch(Sketch):
        def setup(self):
            self.create_canvas(10, 10)

        async def key_pressed(self, event):
            del event
            raise TypeError("callback failure")

    sketch = FailingEventSketch()
    context = sketch.run(max_frames=0)

    with pytest.raises(TypeError, match="callback failure"):
        context.dispatch_keyboard_event(KeyboardEvent(key="a", key_code=65, type="key_pressed"))
