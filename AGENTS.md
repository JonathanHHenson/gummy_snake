# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project Overview

This repository contains `p5py`, a Pythonic creative-coding package inspired by p5.js. The current package distribution name is `p5py_vibe` / `p5py-vibe`.

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

`p5.rust._canvas` owns drawing, presentation, image asset loading/saving,
image-local byte operations, media frame conversion, text, pixels, export, and
native window/input support when built with those capabilities.
Current `WEBGL` support is a Python software-projected path presented through
the canvas runtime, not native accelerated 3D. Backend capabilities distinguish
`software_three_d`, `native_three_d`, `shaders`, and `native_shaders`; do not
imply native 3D or native shader support from `three_d=True`.

Important consequences:

- There is no supported Pillow/Pyglet runtime fallback.
- Bounded/headless runs still use `p5_canvas`; they do not switch to a Python image backend.
- `headless=True` or `--headless` requests offscreen/bounded canvas behavior for tests, CI, and export.
- `headless=False` or `--interactive` requests native interactive canvas behavior where the installed extension supports it.
- Missing extension or missing native-window support should raise clear `p5` capability errors with rebuild guidance.
- `p5.rust._canvas` exposes a canvas ABI marker. Python wrappers should reject missing, malformed, or mismatched markers with rebuild guidance before backend construction proceeds.
- GPU unavailable diagnostics should explain whether headless rendering can continue and what interactive/performance impact to expect.

The Python public API must not expose Rust internals or depend on a concrete renderer in user-facing functions.

## Package Workflow

This project uses `uv`. Use `uv` for Python dependency and command execution:

```sh
uv sync --dev
uv run ruff check .
uv run ruff format .
uv run mypy src
uv run pytest
uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1
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
docs/getting_started/ user learning path and first-sketch material
docs/reference/      public API reference grouped by topic
docs/contribute/     architecture, runtime, testing, and maintainer workflow
.scratch/backlog/             TOML PBIs grouped by numbered epic
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

Prefer Pythonic convenience APIs in user-facing examples and docs when they improve clarity:

- decorator sketches: `@p5.setup`, `@p5.draw`, `@p5.on("key_pressed")`, or `app = p5.sketch()`
- property facades: `p5.current.width`, `p5.mouse.position`, `p5.keyboard.is_down("a")`
- context managers: `with p5.style(...):`, `with p5.transform(...):`, and `with p5.pushed():`
- Python protocols: vector operators, event vector properties, and image indexing where appropriate
- dense-loop fast path: `p5.fast()` / `Sketch.fast()` for hot drawing loops where repeated global-mode dispatch would dominate

Keep the older function-passing and direct state-function APIs working for compatibility, but do not make them the only documented path for new Python-first examples.

`p5.fast()` is a public frame-local facade, not a Rust escape hatch. It should preserve the current public style/transform state and compose with `style()`, `transform()`, and `pushed()` while reducing context lookup and flexible argument-normalization overhead for dense 2D primitive/image/text loops.

Async-compatible lifecycle callbacks are supported. `preload`, `setup`, `draw`, event callbacks, and plugin hooks may be `async def`. Async asset helpers such as `load_image_async`, `load_json_async`, `load_model_async`, and `load_sound_async` are awaitable compatibility wrappers over the current canvas-owned runtime. Do not move Rust canvas-owned objects or active `SketchContext` state to arbitrary worker threads when extending async behavior; the canvas runtime is not generally thread-sendable.

Public closed-set values should be modeled as enums, not untyped constants. Keep p5-style uppercase public names such as `CENTER`, `WEBGL`, and `BLEND` as enum members exported from `src/p5/constants.py`, and expose the enum classes for type annotations. Prefer `StrEnum` for string-valued drawing/API modes and `IntEnum` only where numeric semantics are part of the public API, such as keyboard key codes.

When adding or changing enum-backed public values:

- update annotations at the API boundary and internal state objects to use the enum type rather than `str` or `int`
- keep `src/p5/__init__.py` explicit imports and `__all__` entries in sync
- update `docs/reference/constants_and_enums.md` and any topic-specific reference docs that mention the value
- avoid reintroducing loose `Literal[...]` or raw constant groups when a reusable enum better expresses the closed set

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

p5py distinguishes logical canvas dimensions from physical backing-buffer dimensions.

- `width()` and `height()` report logical p5 dimensions.
- `pixel_density()` controls physical backing scale.
- `display_density()` reports native display scale when available.
- `load_pixels()` and `update_pixels()` operate on physical top-left-oriented RGBA buffers.
- `load_pixel_bytes()` is the lower-copy readback path for pixel workflows that do not need a list.

Do not regress Retina/HiDPI behavior when changing runtime, renderer, pixels, export, images, or input coordinate handling. See `docs/contribute/runtime.md`.

Loaded images may keep a Rust-managed asset attached to the public `Image`
object until pixel mutation. Use stable `Image.cache_key` values for Python
image caches, never `id(image)`, and preserve bounded Rust image/texture cache
lifecycle behavior.

Image-local resize, mask, filter, crop/copy, and alpha compositing should keep
delegating bulk RGBA byte work to `p5_canvas`. Canvas `get(x, y)`,
`get(x, y, w, h)`, `set(...)`, and full-canvas `filter(...)` should use Rust
region/filter operations where practical instead of reconstructing a full
Python `Image`. Optional media helpers may depend on the `media` extra, but
grayscale/BGR/BGRA frame-to-RGBA conversion is a Rust canvas kernel once a
contiguous decoded frame buffer exists.

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
- dev tools include `pytest`, `pytest-cov`, `ruff`, and `mypy`
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
uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1
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
uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1
```

For coverage reporting:

```sh
uv run pytest --cov=p5 --cov-report=term-missing --cov-report=xml
```

For native interactive changes, run a representative example with `--interactive` on a desktop build when practical and document any manual validation.

Benchmark tests are opt-in:

```sh
uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_api_overhead_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_image_pipeline_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_webgl_3d_perf.py --run-benchmarks
```

Canvas benchmark scenarios must average at least 120 FPS. Treat failures below
that floor as optimization work, not as flaky thresholds to loosen. Baseline
snapshots live in `tests/benchmark/baselines/`; keep captured baseline values as
measured and record whether they meet the 120 FPS floor.
API overhead benchmarks should compare global-mode, object-oriented sketch,
context-direct, `fast()`, and renderer-direct dispatch paths.
Renderer/runtime diagnostics should expose counters through public Python APIs
such as `renderer_performance_counters()` rather than leaking unstable Rust
details. Keep fallback-boundary benchmark scenes and
`docs/contribute/runtime_diagnostics.md` aligned when renderer paths change.
Resource lifecycle stress tests are opt-in:

```sh
uv run pytest tests/stress --run-stress -q -s
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
- long-running resource lifecycle checks: `tests/stress/` with explicit opt-in markers

## Documentation Expectations

Update docs when changing architecture, public APIs, runtime behavior, rendering behavior, backend/canvas behavior, packaging, or compatibility status.

Relevant docs include:

```text
docs/getting_started/index.md
docs/getting_started/installation.md
docs/getting_started/core_concepts.md
docs/reference/index.md
docs/reference/lifecycle.md
docs/reference/drawing.md
docs/reference/assets_and_pixels.md
docs/reference/input_and_events.md
docs/reference/constants_and_enums.md
docs/reference/compatibility.md
docs/contribute/index.md
docs/contribute/architecture.md
docs/contribute/backend_renderer.md
docs/contribute/runtime.md
docs/contribute/runtime_diagnostics.md
docs/contribute/build_capabilities.md
docs/contribute/testing.md
docs/contribute/documentation.md
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
[<pbi_title>]
description = '''
As a ...,
I want ...,
So that ...
'''
acceptance_criteria = '''
...
'''
priority = 'high|medium|low'
status = 'TODO|IN_PROGRESS|DONE'

[<pbi_title>.<task_title>]
order = 1
status = 'TODO|IN_PROGRESS|DONE'
description = '''
...
'''
```

When completing work that corresponds to backlog items, update both the parent PBI status and task statuses.

Allowed status values are:

```text
TODO
IN_PROGRESS
DONE
```

Validate backlog TOML after edits:

```sh
uv run python -c "from pathlib import Path; import tomllib; [tomllib.load(p.open('rb')) for p in sorted(Path('.scratch/backlog').glob('**/*.toml'))]; print('Backlog TOML parsed successfully')"
```

## Safety Notes

- Keep changes focused on the requested task.
- Do not modify the sibling `p5.js` repository unless explicitly asked.
- Do not commit changes unless explicitly asked.
- Do not remove or overwrite generated/user files unless you are sure they are artifacts from your own validation commands.
- Do not reintroduce Pillow/Pyglet fallback paths unless the user explicitly asks for a rollback or compatibility experiment.
- Do not add browser, JavaScript, HTML, or DOM-based implementation paths.
