# p5py

[![PyPI](https://img.shields.io/pypi/v/p5py-vibe.svg)](https://pypi.org/project/p5py-vibe/)
[![Python Versions](https://img.shields.io/pypi/pyversions/p5py-vibe.svg)](https://pypi.org/project/p5py-vibe/)
[![License: LGPL-2.1](https://img.shields.io/badge/License-LGPL--2.1-blue.svg)](license.txt)
[![CI](https://github.com/JonathanHHenson/p5.py/actions/workflows/ci.yml/badge.svg)](https://github.com/JonathanHHenson/p5.py/actions/workflows/ci.yml)
[![Downloads](https://img.shields.io/pypi/dm/p5py-vibe.svg)](https://pypi.org/project/p5py-vibe/)

`p5py` is a friendly Python creative-coding library inspired by p5.js. It is for
people who want to sketch with code: draw shapes, animate motion, react to input,
load images, play with pixels, and make small visual experiments without first
building a full app.

The public API is Python-first. Function names use `snake_case`, sketches are
ordinary Python files, and the renderer is powered by the packaged Rust canvas
runtime.

## Install

```sh
pip install p5py-vibe
```

Install optional media helpers when you need camera, video, or sound-related
extras:

```sh
pip install "p5py-vibe[media]"
```

## First Sketch

Create a file named `circle_sketch.py`:

```python
import p5


@p5.setup
def setup() -> None:
    p5.create_canvas(400, 300)
    p5.no_stroke()


@p5.draw
def draw() -> None:
    p5.background(245)
    p5.fill(255, 90, 90)
    p5.circle(200, 150, 100)


p5.run()
```

Run it:

```sh
python circle_sketch.py
```

For repeatable scripts, use a bounded headless render:

```python
p5.run(headless=True, max_frames=1)
```

Callbacks can also be `async def`, which is useful with async-compatible asset
helpers:

```python
image = None


@p5.preload
async def preload() -> None:
    global image
    image = await p5.load_image_async("sprite.png")
```

## What You Can Make

- 2D drawings with shapes, curves, color, transforms, and blend modes.
- Animated sketches using the familiar `setup()` and `draw()` lifecycle.
- Decorator-based sketches, async-compatible callbacks, and object-oriented
  `Sketch` subclasses.
- Image and pixel experiments, including canvas export.
- Text, font measurement, and accessibility descriptions.
- Interactive sketches with mouse, keyboard, and touch state when native window
  support is available.
- WEBGL-style 3D sketches with primitives, lights, materials, models, textures,
  and shader objects on the current software-projected 3D path.
- Small games and visual toys using the examples as starting points.

Loaded images keep their Rust-managed asset until you mutate pixels, so normal
`load_image(); image(...)` sprite drawing can stay on the fast renderer path.
For pixel effects, `load_pixels()` keeps the compatibility list API and
`load_pixel_bytes()` provides a bytes readback path; `update_pixels()` accepts
lists and buffer-like inputs such as `bytes`, `bytearray`, and `memoryview`.

## Learn More

- [Getting started](docs/getting_started/index.md)
- [Examples](examples/README.md)
- [API reference](docs/reference/index.md)
- [Contributor docs](docs/contribute/index.md)

## For Contributors

This repository uses `uv` for Python commands:

```sh
uv sync --dev
uv run ruff check .
uv run mypy src
uv run pytest
```

The canvas runtime is a required PyO3 extension:

```sh
uvx maturin develop --manifest-path crates/p5_canvas/Cargo.toml --module-name p5.rust._canvas --python-source src --features extension-module
```

The contributor documentation explains the architecture, lifecycle, testing
workflow, and release shape in more detail:

- [Contributor guide](docs/contribute/index.md)
- [Architecture](docs/contribute/architecture.md)
- [Runtime model](docs/contribute/runtime.md)
- [Testing and CI](docs/contribute/testing.md)

Performance benchmarks are opt-in:

```sh
uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_api_overhead_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_image_pipeline_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_webgl_3d_perf.py --run-benchmarks
```

Canvas benchmark scenarios are expected to average at least 120 FPS. Failures
below that floor are intentional optimization signals. Machine-specific baseline
snapshots live in `tests/benchmark/baselines/`.

## Compatibility

`p5py` is inspired by p5.js, but it is not a browser port. It does not include
DOM helpers, browser-only APIs, JavaScript aliases, or a Pillow/Pyglet fallback.
Unsupported features raise explicit package errors so sketches fail clearly.
