import pytest

from gummysnake import Sketch
from gummysnake.events.input_state import KeyboardEvent


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
