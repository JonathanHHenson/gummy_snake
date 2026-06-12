from p5_py import Sketch


class CounterSketch(Sketch):
    def __init__(self):
        super().__init__(backend="headless")
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
            super().__init__(backend="headless")

        def setup(self):
            self.create_canvas(10, 10)
            self.no_loop()

        def draw(self):
            raise AssertionError("draw should not run after no_loop in setup")

    context = NoLoopSketch().run(max_frames=2)
    assert context.frame_count == 0
