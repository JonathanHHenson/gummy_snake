# Gummy Snake

[![PyPI](https://img.shields.io/pypi/v/gummy-snake.svg)](https://pypi.org/project/gummy-snake/)
[![Python Versions](https://img.shields.io/pypi/pyversions/gummy-snake.svg)](https://pypi.org/project/gummy-snake/)
[![License: LGPL-2.1](https://img.shields.io/badge/License-LGPL--2.1-blue.svg)](license.txt)
[![Downloads](https://img.shields.io/pypi/dm/gummy-snake.svg)](https://pypi.org/project/gummy-snake/)

Gummy Snake is a playful Python toolkit for creative coding and small games. It
is for people who want to sketch with code: draw shapes, animate motion, react
to input, load sprites, play with pixels, and build visual toys without first
building a full app.

The public API is Python-first. Function names use `snake_case`, sketches are
ordinary Python files, and the renderer is powered by the packaged Rust canvas
runtime.

## Install

```sh
pip install gummy-snake
```

Install optional media helpers when you need camera, video, or sound-related
extras:

```sh
pip install "gummy-snake[media]"
```

## First Sketch

Create a file named `circle_sketch.py`:

```python
import gummysnake as gs


@gs.setup
def setup() -> None:
    gs.create_canvas(400, 300)
    gs.no_stroke()


@gs.draw
def draw() -> None:
    gs.background(245)
    gs.fill(255, 90, 90)
    gs.circle(200, 150, 100)


gs.run()
```

Run it:

```sh
python circle_sketch.py
```

For repeatable scripts, use a bounded headless render:

```python
gs.run(headless=True, max_frames=1)
```

Callbacks can also be `async def`, which is useful with async-compatible asset
helpers:

```python
image = None


@gs.preload
async def preload() -> None:
    global image
    image = await gs.load_image_async("sprite.png")
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
- Software 3D sketches with primitives, lights, materials, models, textures,
  and shader objects on the current Rust-backed software 3D path.
- Small games and visual toys using the examples as starting points.

Loaded images keep their Rust-managed asset until you mutate pixels, so normal
`load_image(); image(...)` sprite drawing can stay on the fast renderer path.
Image-local resize, mask, filter, crop/copy, and alpha compositing delegate
bulk byte work to the Rust canvas extension while keeping the Python `Image`
API and version semantics.
For pixel effects, `load_pixels()` returns a list-based pixel buffer and
`load_pixel_bytes()` provides a bytes readback path; `update_pixels()` accepts
lists and buffer-like inputs such as `bytes`, `bytearray`, and `memoryview`.
Small canvas `get()` and `set()` region operations use Rust region calls where
possible instead of reconstructing the full canvas as a Python image.
For dense drawing loops, `gs.fast()` returns a frame-local facade that keeps
public style/transform state while reducing global-mode dispatch overhead.
Opt-in `enable_performance_diagnostics()` counters can identify readback, pixel
conversion, upload, texture cache, and CPU compositing fallback paths.

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
uvx maturin develop --manifest-path crates/gummy_canvas/Cargo.toml --module-name gummysnake.rust._canvas --python-source src --features extension-module
```

The contributor documentation explains the architecture, lifecycle, testing
workflow, and release shape in more detail:

- [Contributor guide](docs/contribute/index.md)
- [Architecture](docs/contribute/architecture.md)
- [Runtime model](docs/contribute/runtime.md)
- [Runtime diagnostics](docs/contribute/runtime_diagnostics.md)
- [Build capabilities](docs/contribute/build_capabilities.md)
- [API performance policy](docs/contribute/api_performance_policy.md)
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

Long-running resource lifecycle checks are also opt-in:

```sh
uv run pytest tests/stress --run-stress -q -s
```

## Compatibility

Gummy Snake keeps the sketch lifecycle familiar, but it is not a browser port.
It does not include DOM helpers, browser-only APIs, JavaScript aliases, or a
Pillow/Pyglet fallback. Unsupported features raise explicit package errors so
sketches fail clearly.
