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
ordinary Python files, and drawing, export, pixels, text, images, and native
interactive windows are powered by the packaged Rust `gummy_canvas` runtime. On
desktop builds, native windows and input use the SDL3-backed runtime. The Rust
canvas owns the hot renderer state used to construct draw commands, including
the current style, transform stack, image/text state, and GPU command batches.
It also owns the mutable sketch context state for canvas lifecycle fields,
timing, loop/redraw flags, input snapshots, and in-progress shape buffers.

## Install

```sh
pip install gummy-snake
```

Published wheels include the required Rust `gummy_canvas` canvas runtime. Source
or editable installs must build that PyO3 module; there is no Python renderer
fallback for canvas-owned behavior. Local development builds compile SDL3 from
source/static through Rust when native interactive support is enabled, so no
separate system SDL3 install is normally required.

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
- Interactive sketches with SDL3-backed native windows, mouse, keyboard, and
  touch state when native window support is available.
- Software 3D sketches with primitives, lights, materials, models, textures,
  and shader objects on the current Rust-backed software 3D path.
- Small games and visual toys using the examples as starting points.

Loaded images, models/meshes, and sounds keep Rust-managed asset handles behind
friendly Python wrappers. This is intentional for performance: bulk asset bytes,
geometry arrays, parsing, export, and metadata extraction should stay in the
Rust canvas runtime so sketches avoid repeated Python object materialization and
per-element loops. Normal `load_image(); image(...)` sprite drawing can stay on
the fast renderer path, model projection/export can use Rust-owned geometry
without first creating Python `Vec3` objects, untextured software-3D faces can
be submitted directly as Rust/GPU triangles when GPU drawing is available, and
loaded sounds keep their bytes and duration metadata in `CanvasSound` until user
code asks for Python bytes.
Image-local resize, mask, filter, crop/copy, and alpha compositing delegate
bulk byte work to the Rust canvas runtime while keeping the Python `Image`
API and version semantics.
For pixel effects, `load_pixels()` returns a list-based pixel buffer and
`load_pixel_bytes()` provides a bytes readback path; `update_pixels()` accepts
lists and buffer-like inputs such as `bytes`, `bytearray`, and `memoryview`.
Small canvas `get()` and `set()` region operations use Rust region calls instead
of reconstructing the full canvas as a Python image.
For dense drawing loops, `gs.fast()` returns a frame-local facade that keeps
public style/transform state while reducing global-mode dispatch overhead.
Opt-in `enable_performance_diagnostics()` counters can identify readback, pixel
conversion, upload, texture cache, and CPU compositing fallback paths.
HiDPI/Retina rendering keeps sketch coordinates logical while physical pixel
buffers and GPU vertices are scaled by `pixel_density()`.

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

The canvas runtime is a required PyO3 module for development/source installs:

```sh
uvx maturin develop --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
```

The refactored Python package is split by responsibility: public API modules in
`src/gummysnake/api/`, `SketchContext` mixins in `src/gummysnake/_context/`,
lifecycle code in `src/gummysnake/sketch/`, enum-backed constants in
`src/gummysnake/constants/`, and thin canvas backend/renderer facades over the
implementation modules in `src/gummysnake/backend/_canvas/`. The native desktop
runtime itself lives in `crates/gummy_canvas`, owns sketch context state, canvas
draw state, and command construction, and uses SDL3 for windowing, resizing, and
input event collection. Python keeps the public API, callbacks, plugin hooks,
and friendly wrapper objects.

The contributor documentation explains the architecture, lifecycle, testing
workflow, and release shape in more detail:

- [Contributor guide](docs/contribute/index.md)
- [Architecture](docs/contribute/architecture.md)
- [Backend and renderer boundaries](docs/contribute/backend_renderer.md)
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
uv run pytest tests/benchmark/test_model_export_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_webgl_3d_perf.py --run-benchmarks
```

Canvas and WEBGL frame-style benchmark scenarios are expected to average at
least 120 FPS. Failures below that floor are intentional optimization signals.
Model export benchmarks use a memory budget for streaming OBJ/STL output.
Machine-specific baseline snapshots live in `tests/benchmark/baselines/`.

Long-running resource lifecycle checks are also opt-in:

```sh
uv run pytest tests/stress --run-stress -q -s
```

## Compatibility

Gummy Snake keeps the sketch lifecycle familiar, but it is not a browser port.
It does not include DOM helpers, browser-only APIs, JavaScript aliases, or a
Pillow/Pyglet/Python renderer fallback. Unsupported features raise explicit
package errors so sketches fail clearly.
