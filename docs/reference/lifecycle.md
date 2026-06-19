# Sketch Lifecycle

## Decorator Function Mode

```python
import p5


@p5.preload
def preload() -> None:
    pass


@p5.setup
def setup() -> None:
    p5.create_canvas(400, 300)


@p5.draw
def draw() -> None:
    p5.background(255)


p5.run()
```

Use `@p5.on(event_name)` for named event callbacks:

```python
@p5.on(p5.KEY_PRESSED)
def handle_key(event) -> None:
    if event.matches("s"):
        p5.save_canvas("frame.png")
```

For local registration instead of module-level decorators, create a builder:

```python
app = p5.sketch()


@app.setup
def setup() -> None:
    p5.create_canvas(400, 300)


app.run()
```

The older `p5.run(setup=setup, draw=draw, preload=preload)` form is still
supported.

## Class Mode

Subclass `p5.Sketch` when you prefer object-oriented sketches:

```python
import p5


class MySketch(p5.Sketch):
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


@p5.preload
async def preload() -> None:
    global sprite
    sprite = await p5.load_image_async("assets/sprite.png")
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

The `p5.current` facade exposes common active-sketch properties:

- `p5.current.width`
- `p5.current.height`
- `p5.current.frame_count`
- `p5.current.delta_time`
- `p5.current.pixel_density`
- `p5.current.display_density`
- `p5.current.is_looping`
