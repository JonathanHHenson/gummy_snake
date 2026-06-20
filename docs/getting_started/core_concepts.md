# Core Concepts

## Canvas

`create_canvas(width, height)` creates the drawing surface. `gs.current.width`
and `gs.current.height` return the logical canvas size while a sketch is active.
The older `width()` and `height()` functions remain available.

```python
gs.create_canvas(640, 360)
```

Use `pixel_density()` when you need to control the physical backing buffer for
HiDPI output.

## State

Drawing commands use the current style and transform state:

```python
gs.fill(255, 0, 0)
gs.no_stroke()
gs.circle(100, 100, 50)
```

Use `style()` and `transform()` context managers to isolate temporary style or
transform changes:

```python
with gs.style(fill=(255, 0, 0), stroke=None):
    gs.circle(100, 100, 50)

with gs.transform(translate=(200, 100), rotate=0.5):
    gs.rect(0, 0, 80, 40)
```

`push()` / `pop()` and `with gs.pushed():` are also available when you need
manual control over the full drawing state stack.

## Headless Runs

Headless runs use the same Rust canvas runtime, but draw offscreen for tests,
CI, export, and repeatable scripts:

```sh
python my_sketch.py --headless --frames 1
```

## Python Names

Gummy Snake uses Python-style names:

```python
gs.create_canvas(400, 300)
gs.frame_rate(30)
gs.no_loop()
```

CamelCase p5.js names such as `createCanvas()` are not public Gummy Snake APIs.

New examples prefer decorator callbacks, property-style state access, and
Python data-model conveniences such as vector operators and image indexing.
