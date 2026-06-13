# Sketch lifecycle

A `p5-py` sketch follows the familiar p5 lifecycle:

1. create a `SketchContext`
2. run `preload()`
3. run `setup()` once
4. ensure a canvas exists
5. enter the draw loop
6. process events and callbacks until the sketch stops

## Function/global mode

```python
import p5_py as p5


def setup() -> None:
    p5.create_canvas(320, 240)


def draw() -> None:
    p5.background(240)
    p5.circle(160, 120, 40)


p5.run(setup=setup, draw=draw)
```

## Object-oriented mode

```python
from p5_py import Sketch


class MySketch(Sketch):
    def setup(self) -> None:
        self.create_canvas(320, 240)

    def draw(self) -> None:
        self.background(240)
        self.circle(160, 120, 40)


MySketch().run()
```

## Loop control

Use these APIs to control frame execution:

- `frame_rate()`
- `frame_count()`
- `delta_time()`
- `no_loop()`
- `loop()`
- `redraw()`
- `is_looping()`

Headless runs are useful for tests and export:

```python
context = p5.run(setup=setup, draw=draw, backend="headless", max_frames=1)
```

## Plugin lifecycle hooks

Epic 110 adds optional lifecycle hooks for plugins:

- `before_preload`
- `before_setup`
- `after_setup`
- `before_draw`
- `after_draw`

Plugins can also observe normalized events through:

- `on_mouse_event`
- `on_keyboard_event`
- `on_touch_event`
- `on_event`

See `docs/user/plugins.md` for usage.
