from p5 import Sketch


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
