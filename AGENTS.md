# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project Overview

This repository contains `Gummy Snake`, a Pythonic creative-coding and game-development package. The package distribution name is `gummy-snake`.

The project keeps a familiar sketch lifecycle and drawing model while staying native Python at the public API boundary, typed, testable, backend-agnostic for sketch authors, and packaged around the required Rust `gummy_canvas` runtime.

Do not add JavaScript, HTML, DOM APIs, browser-only APIs, or browser runtime dependencies.

## Current Runtime Model

The current runtime is canvas-first:

```text
Python sketch shell:
  user sketch
    -> Sketch / FunctionSketch lifecycle
    -> SketchContext

Python canvas adapters:
  SketchContext
    -> CanvasBackend
    -> CanvasRenderer owned by CanvasBackend
    -> gummysnake.rust.canvas wrapper

Rust-owned canvas runtime:
  gummysnake.rust._canvas
    -> crates/gummy_canvas
    -> SketchContextState, canvas state, draw commands, batching,
       GPU/raster rendering, assets, export, pixels, text, SDL3 window/input

user sketch gs.* calls during callbacks
  -> Gummy Snake public API
  -> active SketchContext
  -> CanvasRenderer
  -> gummysnake.rust._canvas
  -> crates/gummy_canvas
```

`gummysnake.rust._canvas` owns drawing, presentation, renderer draw state,
sketch context state for canvas lifecycle/timing/input/shape capture, image
asset loading/saving, image-local byte operations, media frame conversion, text,
pixels, export, and native window/input support when built with those
capabilities. Python `SketchState` is a compatibility facade over that Rust
state plus Python-only API conversion objects, not an independent runtime
mirror. The current native desktop window/input runtime is SDL3-backed
inside `crates/gummy_canvas`; do not reintroduce winit/Tao window loops as the
primary interactive path without an explicit user request and a new experiment
plan.
Current `WEBGL` support is a Rust-backed software 3D path presented through the
canvas runtime, not native accelerated 3D. Backend capabilities distinguish
`software_three_d`, `native_three_d`, `shaders`, and `native_shaders`; do not
imply native 3D or native shader support from `three_d=True`. Rust handles
software-3D projection, shading, sorting, OBJ/model storage, rasterization, and
direct GPU triangle submission for untextured shaded faces when GPU drawing is
available; textured software-3D faces still route through the Rust raster image
path. This is not a native depth-buffered 3D renderer.

Important consequences:

- The `gummy_canvas` canvas runtime is mandatory for canvas-owned behavior.
- There is no supported Pillow/Pyglet/Python renderer fallback.
- Bounded/headless runs still use `gummy_canvas`; they do not switch to a Python image backend.
- `headless=True` or `--headless` requests offscreen/bounded canvas behavior for tests, CI, and export.
- `headless=False` or `--interactive` requests native interactive canvas behavior where the installed runtime supports it.
- Missing canvas runtime should raise clear Gummy Snake capability errors with rebuild guidance; do not add alternate Python runtime paths.
- Missing native-window support should raise clear Gummy Snake capability errors when interactive behavior is requested.
- SDL3 mouse, wheel, and touch coordinates are logical/window coordinates. Rust event payloads should mark them with `coordinates = "logical"` so Python does not divide them by pixel density a second time. Preserve HiDPI input behavior when touching event code.
- Normalize one-character SDL3 key names to lowercase before exposing them to Python so `KeyboardEvent.matches("l")` and similar lifecycle controls remain stable.
- `gummysnake.rust._canvas` exposes a canvas ABI marker. Python wrappers should reject missing, malformed, or mismatched markers with rebuild guidance before backend construction proceeds.
- GPU unavailable diagnostics should explain whether headless rendering can continue and what interactive/performance impact to expect.
- The GPU command encoder mixes primitive and image/text pipelines in a single frame. When adding draw command types or batching behavior, flush batches and restore the expected pipeline/bind groups when switching command families; primitives drawn after text/images must remain visible.
- Projected software-3D coordinates are logical canvas coordinates. Any direct GPU primitive path that consumes those coordinates must scale by `pixel_density()` before submitting physical vertices, or HiDPI/Retina scenes will appear smaller and farther away.

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
crates/gummy_canvas/    required PyO3 canvas runtime module: gummysnake.rust._canvas
crates/gummy_accel/     optional acceleration extension: gummysnake.rust._accelerated
```

Common commands:

```sh
cargo test --manifest-path crates/gummy_canvas/Cargo.toml
uvx maturin develop --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
uvx maturin build --release --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
```

For `gummy_accel`:

```sh
uvx maturin build --release --manifest-path crates/gummy_accel/Cargo.toml --module-name gummysnake.rust._accelerated --python-source src --features extension-module
```

Keep Rust acceleration optional only for features routed through `gummy_accel`. Features owned by `gummy_canvas` may require the canvas runtime because it is mandatory.

## Source Layout

Primary package code lives under:

```text
src/gummysnake/
```

Important areas:

```text
src/gummysnake/api/          public API entry points, global-mode modules, current context/facade helpers
src/gummysnake/_context/     SketchContext method mixins grouped by canvas, input, pixels, shapes, style, text, transforms, and 3D
src/gummysnake/assets/       image package, text/font, data, model, shader, sound, and optional media helpers
src/gummysnake/backend/     backend contracts, registry, canvas facade modules, and split canvas backend/renderer internals
src/gummysnake/constants/    enum-backed public constants and compatibility aliases
src/gummysnake/core/         color, geometry, math, random/noise, state, transforms, data helpers, vectors
src/gummysnake/drawing/      renderer protocols plus software 3D prototype helpers
src/gummysnake/events/       normalized mouse, keyboard, and touch input state
src/gummysnake/pixels/       public pixel buffer helpers and exports
src/gummysnake/plugins/      plugin interfaces and registry
src/gummysnake/rust/         Python wrappers around PyO3 extensions and Rust-backed kernels
src/gummysnake/sketch/       sketch lifecycle runtime, decorator builder, and object-mode facade
src/gummysnake/testing/      package test resources and helpers
```

Other important directories:

```text
tests/unit/          focused API, state, assets, events, Rust wrapper tests
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

`src/gummysnake/__init__.py` should keep explicit imports and explicit `__all__` entries so Zed/Pyright and other static tooling can see package attributes.

Prefer Pythonic convenience APIs in user-facing examples and docs when they improve clarity:

- decorator sketches: `@gs.setup`, `@gs.draw`, `@gs.on("key_pressed")`, or `app = gs.sketch()`
- property facades: `gs.current.width`, `gs.mouse.position`, `gs.keyboard.is_down("a")`
- context managers: `with gs.style(...):`, `with gs.transform(...):`, and `with gs.pushed():`
- Python protocols: vector operators, event vector properties, and image indexing where appropriate
- dense-loop fast path: `gs.fast()` / `Sketch.fast()` for hot drawing loops where repeated global-mode dispatch would dominate

Keep the older function-passing and direct state-function APIs working for older Gummy Snake examples, but do not make them the only documented path for new Python-first examples.

`gs.fast()` is a public frame-local facade, not a Rust escape hatch. It should preserve the current public style/transform state and compose with `style()`, `transform()`, and `pushed()` while reducing context lookup and flexible argument-normalization overhead for dense 2D primitive/image/text loops.

Async-compatible lifecycle callbacks are supported. `preload`, `setup`, `draw`, event callbacks, and plugin hooks may be `async def`. Async asset helpers such as `load_image_async`, `load_json_async`, `load_model_async`, and `load_sound_async` are awaitable wrappers over the current canvas-owned runtime. Do not move Rust canvas-owned objects or active `SketchContext` state to arbitrary worker threads when extending async behavior; the canvas runtime is not generally thread-sendable.

Public closed-set values should be modeled as enums, not untyped constants. Keep Gummy Snake-style uppercase public names such as `CENTER`, `WEBGL`, and `BLEND` as enum members exported from the `src/gummysnake/constants/` package, and expose the enum classes for type annotations. Prefer `StrEnum` for string-valued drawing/API modes and `IntEnum` only where numeric semantics are part of the public API, such as keyboard key codes.

When adding or changing enum-backed public values:

- update annotations at the API boundary and internal state objects to use the enum type rather than `str` or `int`
- keep `src/gummysnake/__init__.py` explicit imports and `__all__` entries in sync
- update `docs/reference/constants_and_enums.md` and any topic-specific reference docs that mention the value
- avoid reintroducing loose `Literal[...]` or raw constant groups when a reusable enum better expresses the closed set

### Preserve Sketch Lifecycle Ownership

Python `Sketch` and `SketchContext` own lifecycle ordering, global-mode
dispatch, plugin hooks, public API validation, and callback invocation. Rust
`SketchContextState` owns mutable canvas lifecycle fields, timing/frame
counters, loop/redraw flags, input snapshots, and shape capture buffers. The
Rust runtime may schedule frames and provide events, but it should not own Gummy
Snake API naming policy or callback/plugin semantics.

Frame rendering should preserve the existing high-level order:

1. update Rust timing/context frame state
2. begin renderer frame
3. run sketch `draw()` and plugin hooks
4. end renderer frame
5. update context after-frame state
6. present when a frame was drawn

### Keep Backend/Renderer Boundaries Clear

Backends own runtime concerns: mode selection, native window/event loop, scheduling, display density, shutdown, and event dispatch.

Renderers own drawing concerns: canvas dimensions, primitives, transforms, images, text, pixels, compositing, readback, and export.

For the current implementation this means:

- `src/gummysnake/backend/canvas.py` stays a thin public `CanvasBackend` composition layer around lifecycle/runtime/event mixins in `src/gummysnake/backend/_canvas/backend/`.
- `src/gummysnake/backend/canvas_renderer.py` stays a thin public `CanvasRenderer` composition layer around drawing mixins in `src/gummysnake/backend/_canvas/renderer/`.
- `CanvasRenderer` mirrors canvas dimensions for adapter compatibility,
  synchronizes Rust `SketchContextState` during resize/create, synchronizes
  Python facade style/transform changes into Rust current renderer state, and
  forwards draw calls to `gummy_canvas`.
- `gummysnake.rust.canvas` handles optional import, health checks, ABI validation, and clear capability failures.
- `crates/gummy_canvas` owns the native SDL3 runtime and rendering implementation.

### Preserve HiDPI Semantics

Gummy Snake distinguishes logical canvas dimensions from physical backing-buffer dimensions.

- `width()` and `height()` report logical sketch dimensions.
- `pixel_density()` controls physical backing scale.
- `display_density()` reports native display scale when available.
- SDL3 pointer/touch events arrive in logical/window coordinates and must remain logical at the Python boundary.
- `load_pixels()` and `update_pixels()` operate on physical top-left-oriented RGBA buffers.
- `load_pixel_bytes()` is the lower-copy readback path for pixel workflows that do not need a list.

Do not regress Retina/HiDPI behavior when changing runtime, renderer, pixels,
export, images, input coordinate handling, or software-3D GPU submission. See
`docs/contribute/runtime.md`.

Loaded images, models/meshes, and sounds should keep Rust-managed asset handles
attached to their public Python wrappers whenever practical. This is a core
performance policy: bulk asset bytes, geometry arrays, parsing, export,
projection, metadata extraction, and future asset processing should stay in
`gummy_canvas` so sketches avoid repeated Python object materialization and
per-element loops. Use stable `Image.cache_key` values for Python image caches,
never `id(image)`, and preserve bounded Rust image/texture cache lifecycle
behavior.

Image-local resize, mask, filter, crop/copy, and alpha compositing should keep
delegating bulk RGBA byte work to `gummy_canvas`. Model projection/export should
prefer `CanvasModel3D` / `CanvasMesh3D` handles over Python mesh materialization.
Sound metadata and bytes should prefer `CanvasSound` handles while Python keeps
friendly playback controls until audio playback itself moves into the runtime.
Canvas `get(x, y)`,
`get(x, y, w, h)`, `set(...)`, and full-canvas `filter(...)` should use Rust
region/filter operations where practical instead of reconstructing a full
Python `Image`. Optional media helpers may depend on the `media` extra, but
grayscale/BGR/BGRA frame-to-RGBA conversion is a Rust canvas kernel once a
contiguous decoded frame buffer exists.

### Keep Unsupported Browser APIs Out Of The Public API

The project is Python-first, not a direct JavaScript port.

Excluded APIs include:

- DOM and browser element helpers
- browser-only APIs
- `XML`
- `Table`
- `TableRow`

Do not add public compatibility stubs for browser-only or p5.js-specific APIs.
Implement native Gummy Snake features with Pythonic names, or leave the name
absent from public exports until the feature exists.

## Dependencies

Prefer dependencies already present in `pyproject.toml` and the Rust crate manifests.

Current Python project dependencies are intentionally minimal:

- core installs should not require NumPy; ndarray interoperability uses the optional
  `numpy` extra and dev/test environments install NumPy explicitly
- drawing, presentation, assets, pixels, export, numeric mesh/model processing,
  and media frame conversion are supplied by the packaged Rust canvas runtime
- optional media support uses the `media` extra
- dev tools include `numpy`, `pytest`, `pytest-cov`, `ruff`, and `mypy`
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
cargo test --manifest-path crates/gummy_canvas/Cargo.toml
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
uv run pytest --cov=gummysnake --cov-report=term-missing --cov-report=xml
```

For native interactive changes, run a representative example with `--interactive` on a desktop build when practical and document any manual validation.

Benchmark tests are opt-in:

```sh
uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_api_overhead_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_image_pipeline_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_model_export_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_webgl_3d_perf.py --run-benchmarks
```

Canvas benchmark scenarios must average at least 120 FPS. Treat failures below
that floor as optimization work, not as flaky thresholds to loosen. Baseline
snapshots live in `tests/benchmark/baselines/`; keep captured baseline values as
measured and record whether they meet the 120 FPS floor.
Model export benchmarks use a streaming memory budget rather than an FPS floor.
API overhead benchmarks should compare global-mode, object-oriented sketch,
context-direct, `fast()`, and renderer-direct dispatch paths.
WEBGL frame-style benchmarks also use the 120 FPS floor; failures are
optimization work for the Rust software-3D path unless the benchmark is
explicitly measuring a memory budget instead of FPS.
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

Update docs when changing architecture, public APIs, runtime behavior, rendering behavior, backend/canvas behavior, or packaging.

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
docs/contribute/index.md
docs/contribute/architecture.md
docs/contribute/backend_renderer.md
docs/contribute/runtime.md
docs/contribute/runtime_diagnostics.md
docs/contribute/build_capabilities.md
docs/contribute/api_performance_policy.md
docs/contribute/native_3d_plan.md
docs/contribute/testing.md
docs/contribute/documentation.md
```

## Backlog Conventions

Backlog epics use a three-digit prefix to allow insertion between epics, for example:

```text
010_foundation_runtime
091_gummy_canvas_foundation
095_gummy_canvas_migration_release
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
- Do not reintroduce Pillow/Pyglet/Python renderer fallback paths unless the user explicitly asks for a rollback or compatibility experiment.
- Do not add browser, JavaScript, HTML, or DOM-based implementation paths.
