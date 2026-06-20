# Your First Sketch

A sketch usually has two functions:

- `setup()` runs once.
- `draw()` runs every frame.

```python
import gummysnake as gs


@gs.setup
def setup() -> None:
    gs.create_canvas(500, 300)
    gs.no_stroke()


@gs.draw
def draw() -> None:
    gs.background(245)
    gs.fill(255, 80, 80)
    gs.circle(250, 150, 120)


gs.run()
```

The decorators register callbacks on the current sketch module. You can also
use `app = gs.sketch()` when you want a local sketch object, or pass callbacks
explicitly to `gs.run(...)` for older Gummy Snake examples.

## Animate It

Use `frame_count()` to change values over time:

```python
import gummysnake as gs


@gs.setup
def setup() -> None:
    gs.create_canvas(500, 300)


@gs.draw
def draw() -> None:
    gs.background(20)
    x = 250 + gs.sin(gs.current.frame_count * 0.05) * 120
    gs.fill(80, 180, 255)
    gs.circle(x, 150, 60)


gs.run()
```

## Draw Once

Call `no_loop()` in `setup()` when the sketch only needs one frame:

```python
def setup() -> None:
    gs.create_canvas(400, 400)
    gs.no_loop()
```

## Async Setup

Lifecycle and event callbacks may be `async def`, so sketches can await
async-compatible asset helpers:

```python
import gummysnake as gs

sprite = None


@gs.preload
async def preload() -> None:
    global sprite
    sprite = await gs.load_image_async("assets/sprite.png")
```
