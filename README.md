# p5-py

`p5-py` is a Pythonic creative-coding package inspired by p5.js.

It keeps the familiar p5 sketch lifecycle and many p5-style APIs while staying native to Python, backend-agnostic, typed, and testable.

## Status

The current package supports a strong 2D-first workflow, a deterministic headless renderer, a native Pyglet interactive backend, optional WEBGL-style/3D APIs, optional media extras, and optional Rust acceleration for a few compute-heavy paths.

The public API is intentionally Python-first:

- canonical APIs use `snake_case`, such as `create_canvas()` and `frame_rate()`
- p5.js-style aliases such as `createCanvas()` and `frameRate()` delegate to the same implementations
- excluded browser-only APIs fail with explicit `p5_py` exceptions instead of failing indirectly

## Installation

Install the published package with pip:

```sh
pip install p5-py
```

Install optional media support when you need camera/video helpers:

```sh
pip install "p5-py[media]"
```

For local development in this repository, use `uv`:

```sh
uv sync --dev
```

## Quick start

```python
import p5_py as p5


def setup() -> None:
    p5.create_canvas(320, 240)
    p5.no_stroke()


def draw() -> None:
    p5.background(245)
    p5.fill(255, 80, 80)
    p5.circle(160, 120, 80)


p5.run(setup=setup, draw=draw)
```

Run a sketch headlessly for deterministic tests or export flows:

```sh
uv run python examples/basic_shapes.py --backend headless --frames 1
```

## Backends

`p5-py` keeps the user-facing API backend-agnostic.

- `headless` renders deterministically with Pillow and is ideal for tests, CI, and export.
- `pillow` is currently an alias of `headless`.
- `pyglet` opens a native interactive window and presents frames with HiDPI support.

For backend details, see `docs/user/backends.md`.

## Examples

Examples live in `examples/`.

A few useful entry points:

- `examples/basic_shapes.py`
- `examples/bouncing_ball.py`
- `examples/transforms.py`
- `examples/image_text_data.py`
- `examples/pixels_blend_export.py`
- `examples/plugin_hooks.py`
- `examples/webgl_primitives_gallery.py`

See `examples/README.md` for the full index.

## Documentation map

User docs:

- `docs/user/getting_started.md`
- `docs/user/lifecycle.md`
- `docs/user/backends.md`
- `docs/user/compatibility.md`
- `docs/user/images_and_pixels.md`
- `docs/user/events.md`
- `docs/user/plugins.md`

Technical docs:

- `docs/technical/testing.md`
- `docs/technical/releasing.md`
- `docs/technical/hidpi_rendering.md`
- `docs/technical/native_pyglet_renderer.md`
- `docs/technical/rust_acceleration.md`
- `docs/technical/advanced_3d_media_strategy.md`
- `docs/technical/project_plan.md`

## Development workflow

Common local commands:

```sh
uv run ruff check .
uv run ruff format .
uv run mypy src
uv run pytest
uv run python examples/basic_shapes.py --backend headless --frames 1
uv build
```

Equivalent shortcuts are available in `Makefile`:

```sh
make lint
make test-fast
make test
make typecheck
make build
```

## Compatibility policy

`p5-py` aims to keep the p5 mental model while remaining idiomatic Python.

- Use the snake_case APIs as the canonical interface.
- Use camelCase aliases when porting or teaching from p5.js material.
- DOM and browser-only features are excluded.
- Unsupported compatibility stubs raise explicit package-specific errors.

See `docs/user/compatibility.md` for details.
