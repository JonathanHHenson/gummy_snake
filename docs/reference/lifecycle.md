# Sketch Lifecycle

## Decorator Function Mode

```python
import gummysnake as gs


@gs.preload
def preload() -> None:
    pass


@gs.setup
def setup() -> None:
    gs.create_canvas(400, 300)


@gs.draw
def draw() -> None:
    gs.background(255)


gs.run()
```

Use `@gs.on(event_name)` for named event callbacks:

```python
@gs.on(gs.KEY_PRESSED)
def handle_key(event) -> None:
    if event.matches("s"):
        gs.save_canvas("frame.png")
```

For local registration instead of module-level decorators, create a builder:

```python
app = gs.sketch()


@app.setup
def setup() -> None:
    gs.create_canvas(400, 300)


app.run()
```

The older `gs.run(setup=setup, draw=draw, preload=preload)` form is still
supported.

## Class Mode

Subclass `gs.Sketch` when you prefer object-oriented sketches. Common canvas,
shape, style, transform, image, text, input, timing, and media helpers are
available as explicit `self.*` forwarding methods rather than dynamic attribute
magic:

```python
import gummysnake as gs


class MySketch(gs.Sketch):
    def setup(self) -> None:
        self.create_canvas(400, 300)

    def draw(self) -> None:
        self.background(255)


MySketch().run()
```

## Async Callbacks

Lifecycle callbacks, event callbacks, and plugin hooks may be `async def`.
Awaitable callbacks are run to completion by the synchronous canvas runtime.

```python
sprite = None


@gs.preload
async def preload() -> None:
    global sprite
    sprite = await gs.load_image_async("assets/sprite.png")
```

## Lifecycle Functions

- `run(setup=None, draw=None, preload=None, headless=None, max_frames=None)`
- `sketch(headless=None)`
- `preload(callback)`
- `setup(callback)`
- `draw(callback)`
- `on(event_name)`
- `no_loop()`
- `loop()`
- `redraw()`
- `is_looping()`
- `frame_count()`
- `frame_rate(fps=None)`
- `get_target_frame_rate()`
- `delta_time()`
- `millis()`

## Canvas Size

- `create_canvas(width, height, renderer=P2D, pixel_density=None)`
- `resize_canvas(width, height, pixel_density=None)`
- `width()`
- `height()`
- `window_width()`
- `window_height()`
- `display_width()`
- `display_height()`
- `pixel_density(value=None)`
- `display_density()`

`window_width()` and `window_height()` report the active logical canvas size.
`display_width()` and `display_height()` scale that logical size by the native
display density when a window backend can report one; headless sketches use
deterministic canvas dimensions.

The `gs.current` facade exposes common active-sketch properties:

- `gs.current.width`
- `gs.current.height`
- `gs.current.frame_count`
- `gs.current.delta_time`
- `gs.current.pixel_density`
- `gs.current.display_density`
- `gs.current.is_looping`
