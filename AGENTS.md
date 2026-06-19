# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project Overview

This repository contains `p5-py`, a Pythonic creative-coding package inspired by p5.js.

The project keeps the familiar p5 sketch lifecycle and p5-style drawing model while staying native Python at the public API boundary, typed, testable, backend-agnostic for sketch authors, and packaged around the required Rust `p5_canvas` runtime.

Do not add JavaScript, HTML, DOM APIs, browser-only APIs, or browser runtime dependencies.

## Current Runtime Model

The current runtime is canvas-first:

```text
user sketch
  -> p5 public API
  -> Sketch / SketchContext
  -> CanvasBackend + CanvasRenderer Python adapters
  -> PyO3 extension p5.rust._canvas
  -> crates/p5_canvas Rust runtime and renderer
```

`p5.rust._canvas` owns drawing, presentation, image asset loading/saving, text, pixels, export, and native window/input support when built with those capabilities.

Important consequences:

- There is no supported Pillow/Pyglet runtime fallback.
- Bounded/headless runs still use `p5_canvas`; they do not switch to a Python image backend.
- `headless=True` or `--headless` requests offscreen/bounded canvas behavior for tests, CI, and export.
- `headless=False` or `--interactive` requests native interactive canvas behavior where the installed extension supports it.
- Missing extension or missing native-window support should raise clear `p5` capability errors with rebuild guidance.

The Python public API must not expose Rust internals or depend on a concrete renderer in user-facing functions.

## Package Workflow

This project uses `uv`. Use `uv` for Python dependency and command execution:

```sh
uv sync --dev
uv run ruff check .
uv run ruff format .
uv run mypy src
uv run pytest
uv run python examples/basic_shapes.py --headless --frames 1
```

Useful Make targets mirror the same workflow:

```sh
make lint
make format
make typecheck
make test-fast
make test
make smoke
make check
```

Do not use raw `pip install` or unmanaged virtual environments unless explicitly requested.

The active Python version is defined by `.python-version` and `pyproject.toml`. The package currently targets Python 3.12+.

## Rust Workflow

Rust code is part of the active runtime, not just a future optimization layer.

Important crates:

```text
crates/p5_canvas/    required PyO3 canvas runtime extension: p5.rust._canvas
crates/p5_accel/     optional acceleration extension: p5.rust._accelerated
```

Common commands:

```sh
cargo test --manifest-path crates/p5_canvas/Cargo.toml
uvx maturin develop --manifest-path crates/p5_canvas/Cargo.toml --module-name p5.rust._canvas --python-source src --features extension-module
uvx maturin build --release --manifest-path crates/p5_canvas/Cargo.toml --module-name p5.rust._canvas --python-source src --features extension-module
```

For `p5_accel`:

```sh
uvx maturin build --release --manifest-path crates/p5_accel/Cargo.toml --module-name p5.rust._accelerated --python-source src --features extension-module
```

Keep Rust acceleration optional only for features routed through `p5_accel`. Features owned by `p5_canvas` may require the canvas extension because it is the runtime.

## Source Layout

Primary package code lives under:

```text
src/p5/
```

Important areas:

```text
src/p5/api/          global-mode API, current context access, compatibility stubs
src/p5/assets/       image, text/font, data, model, shader, sound/media helpers
src/p5/backends/     canvas backend adapter, renderer adapter, backend construction
src/p5/core/         color, geometry, math, random/noise, state, transforms, vectors
src/p5/drawing/      renderer protocols plus 3D/software prototype helpers
src/p5/events/       normalized mouse, keyboard, and touch input state
src/p5/plugins/      plugin interfaces and registry
src/p5/rust/         Python wrappers around PyO3 extensions
src/p5/testing/      package test resources and helpers
```

Other important directories:

```text
tests/unit/          focused API, state, compatibility, assets, events, Rust wrapper tests
tests/contracts/     backend and renderer contract behavior
tests/golden/        deterministic render comparisons
tests/integration/   end-to-end sketch/rendering behavior
tests/benchmark/     opt-in performance tests
examples/            runnable sketches and smoke-test entry points
docs/user/           user-facing documentation
docs/technical/      architecture, testing, release, and migration notes
backlog/             TOML PBIs grouped by numbered epic
crates/              Rust runtime and acceleration crates
```

Generated artifacts such as `__pycache__/`, compiled `.so` files, build directories, benchmark output, and example image output should not be committed unless the user explicitly asks.

## Architecture Principles

### Keep the Public API Pythonic

Canonical APIs use `snake_case`, for example:

```python
create_canvas()
frame_rate()
no_loop()
pixel_density()
```

Do not export p5.js-style camelCase aliases such as `createCanvas()`, `frameRate()`, `noLoop()`, or `pixelDensity()`. Convert examples and ports to `snake_case`.

`src/p5/__init__.py` should keep explicit imports and explicit `__all__` entries so Zed/Pyright and other static tooling can see package attributes.

### Preserve Sketch Lifecycle Ownership

Python `Sketch` and `SketchContext` own lifecycle ordering, global-mode dispatch, state, plugin hooks, timing, and callback invocation. The Rust runtime may schedule frames and provide events, but it should not own p5 API naming policy or sketch semantics.

Frame rendering should preserve the existing high-level order:

1. update timing/context frame state
2. begin renderer frame
3. run sketch `draw()` and plugin hooks
4. end renderer frame
5. update context after-frame state
6. present when a frame was drawn

### Keep Backend/Renderer Boundaries Clear

Backends own runtime concerns: mode selection, native window/event loop, scheduling, display density, shutdown, and event dispatch.

Renderers own drawing concerns: canvas dimensions, primitives, transforms, images, text, pixels, compositing, readback, and export.

For the current implementation this means:

- `CanvasBackend` stays a thin adapter around lifecycle/runtime/event concerns.
- `CanvasRenderer` translates Python state into bridge payloads and mirrors canvas dimensions.
- `p5.rust.canvas` handles optional import, health checks, and clear capability failures.
- `crates/p5_canvas` owns the native runtime and rendering implementation.

### Preserve HiDPI Semantics

p5-py distinguishes logical canvas dimensions from physical backing-buffer dimensions.

- `width()` and `height()` report logical p5 dimensions.
- `pixel_density()` controls physical backing scale.
- `display_density()` reports native display scale when available.
- `load_pixels()` and `update_pixels()` operate on physical top-left-oriented RGBA buffers.

Do not regress Retina/HiDPI behavior when changing runtime, renderer, pixels, export, images, or input coordinate handling. See `docs/technical/hidpi_rendering.md`.

### Keep Compatibility Explicit

The project is p5-inspired, not a direct JavaScript port.

Excluded APIs include:

- DOM and browser element helpers
- browser-only APIs
- `p5.XML`
- `p5.Table`
- `p5.TableRow`

Unsupported or excluded public compatibility stubs should raise clear package-specific errors, normally `UnsupportedFeatureError` or `BackendCapabilityError`, rather than failing indirectly.

## Dependencies

Prefer dependencies already present in `pyproject.toml` and the Rust crate manifests.

Current Python project dependencies are intentionally minimal:

- core runtime dependencies are supplied by the packaged Rust canvas extension
- optional media support uses the `media` extra
- dev tools include `pytest`, `ruff`, and `mypy`
- release tooling uses `maturin`

Add Python dependencies only when justified, and use `uv add` or `uv add --dev` so `pyproject.toml` and `uv.lock` stay in sync.

Add Rust dependencies only to the relevant crate manifest and keep platform/build implications in mind.

## Testing And Validation

Before finishing code changes, run the smallest checks that cover the change. For most Python changes:

```sh
uv run ruff check .
uv run pytest
```

Also run when relevant:

```sh
uv run mypy src
uv run python examples/basic_shapes.py --headless --frames 1
cargo test --manifest-path crates/p5_canvas/Cargo.toml
uv run python scripts/bump_version.py --check
uv build
```

If formatting changes are needed:

```sh
uv run ruff format .
```

For rendering changes, run at least one bounded/headless smoke test:

```sh
uv run python examples/basic_shapes.py --headless --frames 1
```

For native interactive changes, run a representative example with `--interactive` on a desktop build when practical and document any manual validation.

Benchmark tests are opt-in:

```sh
uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks
```

Check Zed diagnostics when practical.

## Test Expectations

Add or update tests when changing behavior.

Prefer deterministic bounded/headless tests for renderer behavior. Use fake modules/window objects for runtime edge cases where possible. Avoid manual-only interactive tests unless the behavior cannot reasonably be covered headlessly.

Good placement:

- pure API/state logic: `tests/unit/`
- backend and renderer promises: `tests/contracts/`
- stable representative output: `tests/golden/`
- user-visible end-to-end flows: `tests/integration/`
- performance-sensitive checks: `tests/benchmark/` with explicit opt-in markers

## Documentation Expectations

Update docs when changing architecture, public APIs, runtime behavior, rendering behavior, backend/canvas behavior, packaging, or compatibility status.

Relevant docs include:

```text
docs/user/backends.md
docs/user/compatibility.md
docs/user/images_and_pixels.md
docs/technical/canvas_required_runtime.md
docs/technical/canvas_migration_release.md
docs/technical/hidpi_rendering.md
docs/technical/p5_canvas_rust_backend.md
docs/technical/rust_acceleration.md
docs/technical/testing.md
docs/technical/project_plan.md
```

## Backlog Conventions

Backlog epics use a three-digit prefix to allow insertion between epics, for example:

```text
010_foundation_runtime
091_p5_canvas_foundation
095_p5_canvas_migration_release
130_remove_pyglet_backend
140_reference_gap_closure
```

Each PBI file uses this TOML shape:

```toml
[my_pbi]
title = "..."
description = '''
As a ...,
I want ...,
So that ...
'''
acceptance_criteria = '''
...
'''
priotity = 'high|medium|low'
status = 'TODO|IN_PROGRESS|DONE'

[my_pbi.task_1]
order = 1
status = 'TODO|IN_PROGRESS|DONE'
description = '''
...
'''
```

The schema intentionally uses the misspelled key `priotity`. Preserve it unless the user explicitly requests a schema migration.

When completing work that corresponds to backlog items, update both the parent PBI status and task statuses.

Allowed status values are:

```text
TODO
IN_PROGRESS
DONE
```

Validate backlog TOML after edits:

```sh
uv run python -c "from pathlib import Path; import tomllib; [tomllib.load(p.open('rb')) for p in sorted(Path('backlog').glob('**/*.toml'))]; print('Backlog TOML parsed successfully')"
```

## Safety Notes

- Keep changes focused on the requested task.
- Do not modify the sibling `p5.js` repository unless explicitly asked.
- Do not commit changes unless explicitly asked.
- Do not remove or overwrite generated/user files unless you are sure they are artifacts from your own validation commands.
- Do not reintroduce Pillow/Pyglet fallback paths unless the user explicitly asks for a rollback or compatibility experiment.
- Do not add browser, JavaScript, HTML, or DOM-based implementation paths.
