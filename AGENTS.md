# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project Overview

This repository contains `Gummy Snake`, a Pythonic creative-coding and game-development package. The package distribution name is `gummy-snake`.

The project keeps a familiar sketch lifecycle, drawing model, and ECS API while staying native Python at the public API boundary, typed, testable, backend-agnostic for sketch authors, and packaged around the required Rust `gummy_canvas` runtime plus its Rust ECS bridge.

Do not add JavaScript, HTML, DOM APIs, browser-only APIs, or browser runtime dependencies.

## Current Runtime Model

The current runtime is canvas-first and ECS-accelerated:

```text
Python sketch shell:
  user sketch
    -> Sketch / FunctionSketch lifecycle
    -> SketchContext

Python public API adapters:
  SketchContext
    -> CanvasBackend
    -> CanvasRenderer owned by CanvasBackend
    -> EcsWorld facade owned by SketchContext
    -> gummysnake.rust.canvas / gummysnake.rust.ecs wrappers

Rust-owned runtime:
  gummysnake.rust._canvas
    -> crates/gummy_canvas
    -> SketchContextState, canvas state, draw commands, batching,
       GPU/raster rendering, assets, export, pixels, text, SDL3 window/input,
       PyO3 bridge classes/functions for ECS
    -> crates/gummy_ecs
    -> canonical ECS entity/component/tag/resource/event storage,
       query matching, schedules, physical plans, spatial indexes,
       deterministic non-UDF system execution

user sketch gs.* drawing calls during callbacks
  -> Gummy Snake public API
  -> active SketchContext
  -> CanvasRenderer
  -> gummysnake.rust._canvas
  -> crates/gummy_canvas

user sketch ecs systems and entity/resource/event calls
  -> Gummy Snake public API / gummysnake.ecs logical-plan API
  -> active SketchContext.ecs / EcsWorld facade
  -> gummysnake.rust._canvas ECS bridge
  -> crates/gummy_ecs
```

`gummysnake.rust._canvas` owns drawing, presentation, renderer draw state,
sketch context state for canvas lifecycle/timing/input/shape capture, image
asset loading/saving, image-local byte operations, media frame conversion, text,
pixels, export, and native window/input support when built with those
capabilities. The same mandatory extension exposes the Rust ECS bridge backed by
`crates/gummy_ecs`, which owns canonical ECS storage, resource/event queues,
query matching, spatial indexes, schedule/physical-plan execution, and ECS
runtime diagnostics. Python `SketchState` is a compatibility facade over Rust
canvas state plus Python-only API conversion objects, not an independent runtime
mirror. Python `EcsWorld` is a public facade for schemas, logical plans, handles,
views, and explicit UDF boundaries, not a component-column mirror. The current
native desktop window/input runtime is SDL3-backed inside `crates/gummy_canvas`;
do not reintroduce winit/Tao window loops as the primary interactive path without
an explicit user request and a new experiment plan.
Current `WEBGL` support is a Rust canvas 3D path presented through the canvas
runtime. Backend capabilities distinguish `software_three_d`, `native_three_d`,
`shaders`, and `native_shaders`; do not imply user-programmable native shader
support from `three_d=True`. Rust handles OBJ/model storage, primitive model
generation, export, fallback software projection/raster paths, and built-in
GPU model pipelines. When GPU drawing is available, built-in unstroked model
and primitive draws should use retained Rust/GPU vertex/index buffers, GPU
transform/projection, GPU depth testing, and built-in material/texture shaders
instead of CPU-projected face payloads.

Important consequences:

- The `gummy_canvas` canvas runtime is mandatory for canvas-owned behavior and for exposing the ECS bridge.
- The `gummy_ecs` Rust crate owns canonical ECS storage and non-UDF system execution.
- There is no supported Pillow/Pyglet/Python renderer fallback.
- There is no supported Python ECS execution fallback for non-UDF systems.
- Bounded/headless runs still use `gummy_canvas`; they do not switch to a Python image backend or Python ECS runtime.
- `headless=True` or `--headless` requests offscreen/bounded canvas behavior for tests, CI, and export.
- `headless=False` or `--interactive` requests native interactive canvas behavior where the installed runtime supports it.
- Missing canvas runtime should raise clear Gummy Snake capability errors with rebuild guidance; do not add alternate Python runtime paths.
- Missing native-window support should raise clear Gummy Snake capability errors when interactive behavior is requested.
- SDL3 mouse, wheel, and touch coordinates are logical/window coordinates. Rust event payloads should mark them with `coordinates = "logical"` so Python does not divide them by pixel density a second time. Preserve HiDPI input behavior when touching event code.
- Normalize one-character SDL3 key names to lowercase before exposing them to Python so `KeyboardEvent.matches("l")` and similar lifecycle controls remain stable.
- `gummysnake.rust._canvas` exposes canvas and ECS ABI markers. Python wrappers should reject missing, malformed, or mismatched markers with rebuild guidance before backend/ECS construction proceeds.
- GPU unavailable diagnostics should explain whether headless rendering can continue and what interactive/performance impact to expect.
- ECS systems are Python-declared logical plans. Rust-executed `@ecs.system` functions are called once at registration with query/resource/event proxies and an active context-manager plan-build session. They must return `None` and record work with field mutation methods, `ecs.do`, `ecs.conditional`/`ecs.when`/`ecs.otherwise`, `ecs.for_each`, and event writer methods. Rust compiles those plans into physical plans and executes them before drawing. Bare `@ecs.udf` declares Rust-backed typed UDFs; only explicit `@ecs.udf(python=True)` UDFs and `@ecs.system(python=True)` systems may execute Python at ECS runtime.
- Do not maintain Python mirrors of component columns. Python entity/resource views should read/write Rust-owned storage, and dense draw-side readback should use batch APIs such as `iter_component_fields()`.
- ECS strict mode should reject non-deterministic duplicate writes. Non-strict mode may use deterministic last-write-wins, count diagnostics, and warn unless `warn_on_ambiguity=False` suppresses logs.
- Spatial ECS APIs must stay generic (`ecs.spatial.neighbors`, `join`, `overlaps`, and algorithm configs such as `HashGrid`, `Quadtree`, `Octree`, and `HilbertCurve`). Do not add bespoke APIs for a single sketch or benchmark.
- The GPU command encoder mixes primitive and image/text pipelines in a single frame. When adding draw command types or batching behavior, flush batches and restore the expected pipeline/bind groups when switching command families; primitives drawn before and after text/images/effects must remain visible. The Rust encoder uses a local `RenderPassBatcher`; if special commands split a frame into multiple render-pass segments, reusable buffer offsets must advance across the whole command encoder so later vertex/image/model uploads do not overwrite data referenced by earlier passes.
- Direct glyphon GPU text is limited to ordered command streams where text can be encoded as a single contiguous glyphon text segment. If later text follows intervening primitives/images/effects, preserve draw order by using the Rust cached line-texture path for that later text rather than queuing multiple glyphon text passes that can corrupt earlier glyph atlas output. Batched cached text-image fallback may atlas many cached line textures into ordered image batches; preserve cache hit/miss and texture upload diagnostics.
- Text metrics and `text_bounds()` must use the same current Python style revision as subsequent drawing. Do not use Rust current-style metric fast paths when the Python `StyleState` object or revision has changed after native/window sync.
- GPU render encoding owns reusable vertex buffers sized to frame demand. When changing primitive, erase, image, or text command encoding, preserve capacity-growth reuse and keep `gpu_vertex_buffer_allocations`, `gpu_vertex_uploads`, `gpu_primitive_batches`, and `gpu_image_batches` meaningful.
- Compact primitive batches may include fill-only primitives, stroked/fill mixed primitive groups, and lines with per-record style and transform payloads. Procedural GPU instance commands should be used where practical for rects, triangles, and axis-aligned ellipses/circles. Preserve retained batch replay, HiDPI scaling, clip/blend ordering, and fallback to vertex-expanded paths for unsupported transforms.
- Ordered sprite batches may carry per-record transforms, source rectangles, tint, sampling, and blend state and may use the Rust image atlas path for small alternating texture sets. Static unchanged full-frame command streams may be retained and reused by the GPU renderer; dynamic image batches must still report texture/cache/upload counters accurately.
- Current renderer performance paths include compact mixed primitive/line/image batches, transformed sprite atlas batches, batched cached text-image atlas fallback, procedural fill-only primitive instances, retained static command-stream replay, skipped no-op pixel uploads, dirty `PixelBuffer` region uploads, direct Rust shape/clip finalization, `gs.fast()` hot-loop dispatch reduction, and retained GPU model buffers. Preserve these paths and their diagnostics when touching code from epics 238-250.
- Fallback software-3D coordinates are logical canvas coordinates. Any direct GPU primitive fallback that consumes those coordinates must scale by `pixel_density()` before submitting physical vertices, or HiDPI/Retina scenes will appear smaller and farther away.
- Unstroked model draws with Rust model handles should use the retained GPU model path when GPU drawing is available and avoid Python face dictionaries, CPU projection/sorting, and CPU shading. Stroked or unsupported model paths may fall back, but diagnostics should make that boundary visible.
- Captured `begin_shape()` buffers live in Rust and should be finalized directly into Rust draw/clip commands. Avoid materializing `shape_vertices()` / `shape_contours()` Python lists on normal renderer paths.

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
crates/gummy_ecs/       Rust ECS storage, schedule, physical-plan, and spatial-index crate linked through gummy_canvas
crates/gummy_accel/     optional acceleration extension: gummysnake.rust._accelerated
```

Common commands:

```sh
cargo test --manifest-path crates/gummy_canvas/Cargo.toml
cargo test --manifest-path crates/gummy_ecs/Cargo.toml
uvx maturin develop --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
uvx maturin develop --release --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
uvx maturin build --release --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
```

For `gummy_accel`:

```sh
uvx maturin build --release --manifest-path crates/gummy_accel/Cargo.toml --module-name gummysnake.rust._accelerated --python-source src --features extension-module
```

Keep Rust acceleration optional only for features routed through `gummy_accel`. Features owned by `gummy_canvas` or `gummy_ecs` may require the canvas runtime because it is mandatory. Use release `maturin develop` or release wheels for benchmark/performance comparisons; a debug/development extension can make ECS spatial systems and renderer benchmarks look dramatically slower.

## Source Layout

Primary package code lives under:

```text
src/gummysnake/
```

Important areas:

```text
src/gummysnake/api/          public API entry points grouped by topic (lifecycle, environment, timing, input, images, pixels, text, compositing, media, models, shaders, sound, three_d), global-mode modules, current context helpers, and compatibility facades
src/gummysnake/context_mixins/     SketchContext method mixins grouped by canvas, input, pixels, shapes, style, text, transforms, and 3D
src/gummysnake/assets/       image package (public Image class in image/core.py), text/font, data, model, shader, sound, and optional media helpers
src/gummysnake/backend/     backend contracts, registry, thin canvas facade modules, and split canvas runtime internals under canvas_runtime/host/ and canvas_runtime/renderer/
src/gummysnake/constants/    enum-backed public constants and compatibility aliases
src/gummysnake/core/         color, geometry, math, random/noise, pixels, input event dataclasses, state, state_facades, transforms, data helpers, vectors
src/gummysnake/drawing/      renderer protocols, renderer3d package, software3d helpers, and retained prototype3d compatibility helpers
src/gummysnake/ecs/          Python ECS public API, dataclass schemas, logical expressions/actions, systems, spatial relation builders, physical payload serialization, and Rust-backed world facade
src/gummysnake/plugins/      plugin interfaces and registry
src/gummysnake/rust/         Python wrappers around PyO3 extensions and Rust-backed kernels
src/gummysnake/sketch/       sketch lifecycle runtime, decorator builder, and explicit object-mode facade forwarding groups under sketch/facade_mixins/
```

Other important directories:

```text
tests/unit/          focused API, state, assets, events, Rust wrapper tests
tests/contracts/     backend and renderer contract behavior
tests/golden/        deterministic render comparisons
tests/integration/   end-to-end sketch/rendering behavior
tests/benchmark/     opt-in performance tests
tests/stress/        opt-in resource lifecycle stress tests
tests/helpers/       shared fake canvas runtimes, renderer fakes, and WebGL test helpers
tests/fixtures/      package-resource and file fixtures used by tests
examples/            runnable sketches and smoke-test entry points; generated output belongs under ignored examples/output/
docs/getting_started/ user learning path and first-sketch material
docs/reference/      public API reference grouped by topic
docs/contribute/     architecture, runtime, testing, and maintainer workflow
.scratch/backlog/             TOML PBIs grouped by numbered epic
crates/              Rust runtime and acceleration crates; gummy_canvas canvas helpers include cache, dirty-state, image batch, text layout, and GPU render-pass batching modules; gummy_ecs owns ECS storage, plans, schedules, and spatial indexes
```

Generated artifacts such as `__pycache__/`, compiled `.so` files, build directories, benchmark output, and example image/data output should not be committed unless the user explicitly asks.

Naming conventions:

- Python implementation packages should use descriptive names rather than adjacent `name.py` plus `_name/` packages. Use `context_mixins` and `facade_mixins` only for actual mixin groups, `facades` for compatibility/export/property-forwarding surfaces, and `canvas_runtime/host` or `canvas_runtime/renderer` for backend/runtime implementation groups.
- Public 3D docs/API use `three_d` where a Python identifier is needed. Existing compatibility modules such as `drawing/renderer3d` and `drawing/software3d` keep their names because they are import paths and type names already used by tests/users.
- Rust may use same-stem `foo.rs` hub files with `foo/` child modules when the hub is an intentional module declaration/re-export boundary. Keep the documented hub list in `scripts/structure_audit.py` and contributor docs in sync if adding new hubs.
- Run `uv run python scripts/structure_audit.py` after source-layout reorganizations to catch stale package names, source test fixtures, generated output policy drift, and confusing Python module/package siblings.

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

`gs.fast()` is a public frame-local facade, not a Rust escape hatch. It should preserve the current public style/transform state and compose with `style()`, `transform()`, and `pushed()` while reducing context lookup and flexible argument-normalization overhead for dense 2D primitive/image/text loops and supported 3D camera/light/transform/material/model loops.

Async-compatible lifecycle callbacks are supported. `preload`, `setup`, `draw`, event callbacks, and plugin hooks may be `async def`. Async asset helpers such as `load_image_async`, `load_json_async`, `load_model_async`, and `load_sound_async` are awaitable wrappers over the current canvas-owned runtime. Do not move Rust canvas-owned objects or active `SketchContext` state to arbitrary worker threads when extending async behavior; the canvas runtime is not generally thread-sendable.

Public closed-set values should be modeled as enums, not untyped constants. Keep Gummy Snake-style uppercase public names such as `CENTER`, `WEBGL`, and `BLEND` as enum members exported from the `src/gummysnake/constants/` package, and expose the enum classes for type annotations. Prefer `StrEnum` for string-valued drawing/API modes and `IntEnum` only where numeric semantics are part of the public API, such as keyboard key codes.

When adding or changing enum-backed public values:

- update annotations at the API boundary and internal state objects to use the enum type rather than `str` or `int`
- keep `src/gummysnake/__init__.py` explicit imports and `__all__` entries in sync
- update `docs/reference/constants_and_enums.md` and any topic-specific reference docs that mention the value
- avoid reintroducing loose `Literal[...]` or raw constant groups when a reusable enum better expresses the closed set

### Keep ECS Rust-Owned And Plan-Driven

The ECS public API is Pythonic, but runtime execution is Rust-owned:

- Components, resources, and events are declared with Python dataclasses. Default
  Python field types map to Rust storage columns, and `typing.Annotated` with
  `gummysnake.ecs.types` selects narrower scalar, vector, or list storage.
- Rust-executed `@ecs.system` functions must have complete annotations and return
  only `None`. The function is called at registration with query/resource/event
  proxies and an active context-local build session; field mutation methods and
  context managers append actions to the logical plan used for explain output and
  serialization. Returned `ecs.Action`/`SystemPlan` trees are migration errors.
- Supported non-UDF nodes include field `set_to`/`increase_by`/`decrease_by`,
  `with ecs.do:`, `with ecs.do(parallel=True):`, `@ecs.system(parallel=True)`,
  `ecs.conditional`, `ecs.when`, `ecs.otherwise`, `ecs.for_each`, typed events,
  structural entity commands, resources, change filters, grouped aggregates,
  `ecs.exists`, `ecs.dt`, `ecs.key_is_down`, and generic `ecs.spatial` relations.
- Python boolean `and` / `or` / `not` and chained comparisons cannot build lazy
  plans. Use `&`, `|`, `~`, `ecs.all_of(...)`, or `ecs.any_of(...)` in systems and
  examples.
- `with ecs.do:` is serial; later actions observe earlier writes.
  `@ecs.system(parallel=True)` and `with ecs.do(parallel=True):` are for
  independent snapshot-style work. Strict mode rejects ambiguous duplicate writes;
  non-strict mode uses deterministic last-write-wins with diagnostics and
  optional warnings.
- Bare `@ecs.udf` declares Rust-backed typed UDFs with `ecs.Expression[T]`
  inputs/outputs and must not execute Python at runtime. Explicit
  `@ecs.udf(python=True)` UDFs and `@ecs.system(python=True)` systems are
  performance-cost boundaries for side effects, external APIs, or operations not
  expressible in the ECS DSL; they are the only ECS runtime work that may execute
  Python.
- Do not add Python fallback execution, Python component-column mirrors, or
  sketch-specific ECS kernels. If a generic operation is missing, design it as a
  logical-plan/Rust physical executor feature and expose generic diagnostics.

### Preserve Sketch Lifecycle Ownership

Python `Sketch` and `SketchContext` own lifecycle ordering, global-mode
dispatch, plugin hooks, public API validation, and callback invocation. Rust
`SketchContextState` owns mutable canvas lifecycle fields, timing/frame
counters, loop/redraw flags, input snapshots, and shape capture buffers. The
Rust runtime may schedule frames, provide events, and execute compiled ECS plans,
but it should not own Gummy Snake API naming policy or callback/plugin semantics.

Frame rendering should preserve the existing high-level order:

1. update Rust timing/context frame state
2. begin renderer frame
3. dispatch plugin `before_ecs`
4. run scheduled ECS systems through Rust physical execution, except explicit UDFs
5. dispatch plugin `after_ecs`
6. dispatch plugin `before_draw`
7. run sketch `draw()`
8. dispatch plugin `after_draw`
9. end renderer frame
10. update context after-frame state
11. present when a frame was drawn

### Keep Backend/Renderer Boundaries Clear

Backends own runtime concerns: mode selection, native window/event loop, scheduling, display density, shutdown, and event dispatch.

Renderers own drawing concerns: canvas dimensions, primitives, transforms, images, text, pixels, compositing, readback, and export.

For the current implementation this means:

- `src/gummysnake/backend/canvas.py` stays a thin public `CanvasBackend` composition layer around lifecycle/runtime/event mixins in `src/gummysnake/backend/canvas_runtime/host/`.
- `src/gummysnake/backend/canvas_renderer.py` stays a thin public `CanvasRenderer` composition layer around drawing mixins/helpers in `src/gummysnake/backend/canvas_runtime/renderer/`; keep bridge, lifecycle, counters, cache, payload-builder, primitive batch-state, and drawing modules focused.
- `CanvasRenderer` mirrors canvas dimensions for adapter compatibility,
  synchronizes Rust `SketchContextState` during resize/create, synchronizes
  Python facade style/transform changes into Rust current renderer state, and
  forwards draw calls to `gummy_canvas`.
- `EcsWorld` validates Python dataclass schemas, builds/serializes logical plans,
  exposes handles/views/resources/events, and delegates canonical storage and
  non-UDF execution to Rust.
- `gummysnake.rust.canvas` handles optional import, health checks, ABI validation, and clear capability failures.
- `gummysnake.rust.ecs` validates the ECS ABI and wraps the ECS bridge objects exposed by `gummy_canvas`.
- `crates/gummy_canvas` owns the native SDL3 runtime and rendering implementation.
- `crates/gummy_ecs` owns ECS storage, schedules, physical execution, resources/events, query matching, and spatial indexes.

### Preserve HiDPI Semantics

Gummy Snake distinguishes logical canvas dimensions from physical backing-buffer dimensions.

- `width()` and `height()` report logical sketch dimensions.
- `pixel_density()` controls physical backing scale.
- `display_density()` reports native display scale when available.
- SDL3 pointer/touch events arrive in logical/window coordinates and must remain logical at the Python boundary.
- `load_pixels()` and `update_pixels()` operate on physical top-left-oriented RGBA buffers.
- `load_pixels()` returns the public `PixelBuffer`, a mutable list-like RGBA byte buffer that tracks dirty byte ranges for efficient update paths.
- `load_pixel_bytes()` is the lower-copy readback path for pixel workflows that do not need list-like mutation.
- `update_pixels()` should pass `bytes`, `bytearray`, `memoryview`, and dirty `PixelBuffer` payloads through Rust buffer/region upload paths without forcing Python `bytes(...)` copies. List inputs remain compatibility paths and should be counted in diagnostics.

Do not regress Retina/HiDPI behavior when changing runtime, renderer, pixels,
export, images, input coordinate handling, GPU model draws, or software-3D GPU
fallback submission. See `docs/contribute/runtime.md`.

Loaded images, models/meshes, and sounds should keep Rust-managed asset handles
attached to their public Python wrappers whenever practical. This is a core
performance policy: bulk asset bytes, geometry arrays, parsing, export,
projection, metadata extraction, and future asset processing should stay in
`gummy_canvas` so sketches avoid repeated Python object materialization and
per-element loops. Use stable `Image.cache_key` values for Python image caches,
never `id(image)`, and preserve bounded Rust image/texture cache lifecycle
behavior.

Image-local resize, mask, filter, crop/copy, and alpha compositing should keep
delegating bulk RGBA byte work to `gummy_canvas`. Model export and built-in
WEBGL drawing should prefer `CanvasModel3D` / `CanvasMesh3D` handles over
Python mesh materialization. Retained GPU model buffers should be keyed by
Rust model identity and reused across frames; per-frame changes should update
small transform/camera/material/light uniforms.
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
  media frame conversion, and ECS storage/physical execution are supplied by the
  packaged Rust runtime
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
uv run python scripts/source_size_audit.py
uv run python scripts/structure_audit.py
cargo test --manifest-path crates/gummy_canvas/Cargo.toml
cargo test --manifest-path crates/gummy_ecs/Cargo.toml
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

For ECS changes, run focused Python and Rust checks plus at least one ECS example:

```sh
uv run ruff check src/gummysnake/ecs tests/unit/test_ecs.py
uv run mypy src/gummysnake/ecs
uv run pytest tests/unit/test_ecs.py -q
cargo test --manifest-path crates/gummy_ecs/Cargo.toml
uv run python examples/10_ecs/firefly_constellation.py --headless --frames 1 --no-save
uv run python examples/10_ecs/crystal_moths.py --headless --frames 1 --no-save
uv run python examples/09_performance/boids_3d.py --headless --frames 1 --no-save
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
uv run pytest tests/benchmark/test_ecs_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_ecs_spatial_perf.py --run-benchmarks
```

The 50k and 100k primitive stress benchmarks are intentionally excluded from
the default canvas benchmark run. Run the high-count suite separately after the
10k primitive gate is healthy:

```sh
uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks --run-high-count-benchmarks -k high_count
```

The high-count test itself still gates progression: it skips 50k until 10k
reaches at least 60 FPS, and skips 100k until 50k reaches at least 30 FPS.

Benchmark helpers for subprocess execution and JSON metric parsing live in
`tests/benchmark/benchmark_helpers.py`; extend them instead of copying benchmark
boilerplate. Canvas backend benchmark scenarios measure native interactive
presentation and must average at least 240 FPS. Headless/offscreen numbers are
useful for export diagnostics, but they are not the runtime performance
acceptance metric. Treat
failures below the interactive floor as optimization work, not as flaky
thresholds to loosen. Recovered variants from epics 246-250 should retain margin
where practical: dense primitives around 320 FPS mean and cached/transformed
images, upload churn, sprite/text overlay, and mixed text/pixel scenes around
300 FPS mean on the baseline machine class. Baseline snapshots live in
`tests/benchmark/baselines/`; keep captured baseline values as measured and
record whether they meet both the 240 FPS floor and any documented margin
target.
Model export benchmarks use a streaming memory budget rather than an FPS floor.
API overhead benchmarks should compare global-mode, object-oriented sketch,
context-direct, `fast()`, and renderer-direct dispatch paths.
WEBGL frame-style benchmarks also use the 240 FPS floor; failures are
optimization work for the Rust 3D/GPU model path or its fallback boundaries
unless the benchmark is explicitly measuring a memory budget instead of FPS.
ECS benchmarks should show non-UDF hot systems running through Rust physical
plans (`ecs_physical_system_runs` > 0) with `ecs_udf_calls` at zero for the hot
path. Spatial ECS benchmarks should report candidate/exact rows and algorithm
counters that match the intended relation shape. Use
`examples/09_performance/boids_3d.py --headless --frames 1 --no-save` as a smoke
path for ECS spatial simulation plus retained WEBGL model drawing.
Renderer/runtime diagnostics should expose counters through public Python APIs
such as `renderer_performance_counters()` and `ecs_diagnostics()` rather than
leaking unstable Rust details. Keep fallback-boundary benchmark scenes and
`docs/contribute/runtime_diagnostics.md` aligned when renderer paths change,
especially `primitive_batch_records`, `primitive_batch_flushes`,
`primitive_batch_max_records`, `image_batch_records`, `image_batch_flushes`, and
`image_batch_max_records`.
GPU region effects should stay ordered with pending draw commands and avoid CPU
readback/upload in the GPU path; update `gpu_region_effect_passes` diagnostics
when adding new region effects. Destination-sampling blend modes must not be
enabled outside the ordered command encoder source/target snapshot path.
Untransformed default-font text uses the Rust-owned glyphon/cosmic-text GPU
path with cached shaped buffers and a glyph atlas when ordering permits it;
batched cached line-texture atlas fallback is the preferred ordered fallback for
large overlays or later text segments. Transformed/custom-font text may use the
internal fallback until those cases are explicitly migrated.
Resource lifecycle stress tests are opt-in:

```sh
uv run pytest tests/stress --run-stress -q -s
```

Check Zed diagnostics when practical.

## Test Expectations

Add or update tests when changing behavior.

Prefer deterministic bounded/headless tests for renderer and ECS behavior. Use fake modules/window objects for runtime edge cases where possible. Avoid manual-only interactive tests unless the behavior cannot reasonably be covered headlessly.

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
docs/reference/ecs.md
docs/reference/constants_and_enums.md
docs/contribute/index.md
docs/contribute/architecture.md
docs/contribute/backend_renderer.md
docs/contribute/runtime.md
docs/contribute/runtime_diagnostics.md
docs/contribute/ecs_architecture.md
docs/contribute/ecs_debugging.md
docs/contribute/build_capabilities.md
docs/contribute/api_performance_policy.md
docs/contribute/text_renderer_decision.md
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
- Do not add Python ECS execution fallbacks or Python component-column mirrors for non-UDF systems.
- Do not add browser, JavaScript, HTML, or DOM-based implementation paths.
