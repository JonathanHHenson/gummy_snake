# Getting started

## Install the package

For normal usage:

```sh
pip install p5-py
```

For media helpers:

```sh
pip install "p5-py[media]"
```

For development in this repository:

```sh
uv sync --dev
```

## Your first sketch

```python
import p5_py as p5


def setup() -> None:
    p5.create_canvas(400, 300)
    p5.frame_rate(60)


def draw() -> None:
    p5.background(250)
    p5.fill(40, 120, 255)
    p5.circle(200, 150, 80)


p5.run(setup=setup, draw=draw)
```

## Running sketches

Interactive window:

```sh
uv run python examples/basic_shapes.py
```

Headless one-frame smoke test:

```sh
uv run python examples/basic_shapes.py --backend headless --frames 1
```

## Choose a sketch style

`p5-py` supports both:

- function/global mode via `p5.run(setup=..., draw=...)`
- object-oriented sketches by subclassing `p5_py.Sketch`

Global mode is convenient for small sketches and tutorials.
Class-based sketches are a good fit for larger stateful sketches and internal extension points.

## What to read next

- `docs/user/lifecycle.md` for the runtime flow
- `docs/user/backends.md` for backend selection
- `docs/user/images_and_pixels.md` for deterministic image and pixel workflows
- `docs/user/events.md` for mouse/keyboard/touch state
- `examples/README.md` for the example index
