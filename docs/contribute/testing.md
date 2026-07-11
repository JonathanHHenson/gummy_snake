# Testing and CI

Use the smallest checks that cover the change.

## Canonical Commands

The [canonical validation matrix](validation.md) is the source of truth for
local, pull-request, publish, native-wheel, and release-candidate gates. Start
with a release runtime, then run the supported comprehensive local gate:

```sh
uv sync --dev
make runtime-develop-release
make check
```

Useful focused commands remain available without duplicating workflow recipes:

```sh
make format-check
make static-analysis
make repository-audits
make test-focused
make test-full
make rust-check
make smoke-release
make package-verify
```

`make check` and every command above are non-mutating to tracked files. `make
format` intentionally reformats files. `make package-verify` builds into a fresh,
ignored `.scratch/package-verify/run.*` workspace and removes only that workspace
when it finishes; it never inspects or removes shared `dist/` artifacts. The normal
test suite leaves benchmark and stress markers opt-in.

For coverage locally:

```sh
uv run pytest --cov=gummysnake --cov-report=term-missing --cov-report=xml
```

## Choosing The Right Check

Use focused checks while developing, then broaden before handing off:

| Change type | Minimum useful check |
| --- | --- |
| Pure Python API/state logic | targeted `uv run pytest tests/unit/...` |
| Public API export changes | unit tests plus `make static-analysis` |
| Backend scheduling or capability behavior | `tests/contracts/` plus relevant unit tests |
| Renderer or pixel behavior | contract or integration test plus a headless smoke example |
| Rust canvas runtime behavior | `cargo test --manifest-path crates/gummy_canvas/Cargo.toml` plus Python wrapper tests |
| ECS API, storage, scheduling, or physical execution | `uv run ruff check src/gummysnake/ecs tests/unit/ecs/test_ecs.py`, `uv run mypy src/gummysnake/ecs`, `uv run pytest tests/unit/ecs/test_ecs.py -q`, and `cargo test --manifest-path crates/gummy_ecs/Cargo.toml` |
| ECS spatial systems or examples | ECS unit/Rust checks plus `uv run python examples/10_ecs/firefly_constellation.py --headless --frames 1 --no-save`, `uv run python examples/10_ecs/crystal_moths.py --headless --frames 1 --no-save`, or `uv run python examples/09_performance/boids_3d.py --headless --frames 1 --no-save` |
| WEBGL or fallback 3D path behavior | focused integration tests plus `tests/benchmark/test_webgl_3d_perf.py --run-benchmarks` when hot paths change |
| Long-running resource lifecycle behavior | `uv run pytest tests/stress --run-stress -q -s` |
| Static-analysis configuration, suppressions, or tooling | `make static-analysis` plus `uv run pytest tests/unit/tooling/test_static_analysis_audit.py` |
| Examples, catalog, or example smoke tooling | `uv run python scripts/structure_audit.py` and the relevant `scripts/example_smoke.py --tier ...` commands |
| Documentation only | link/path review; no full test suite required unless commands changed |
| Source layout, package naming, file splits, or validation-route moves | `make audit`, `uv run python scripts/source_size_audit.py`, and `uv run python scripts/impact_map_audit.py` |
| Synth or FX asset sources | `make assets-check` plus focused synth asset tests |
| Source distribution/package inputs | `make package-verify` (repeatable and isolated) or `make verify-sdist SDIST_DIR=dist` after building when `dist/` has exactly one matching sdist |
| Built wheel, native stubs, or release packaging | `make verify-wheel WHEEL_DIR=dist/canvas` or `make verify-wheel-accel WHEEL_DIR=dist/canvas ACCELERATED_WHEEL_DIR=dist/accelerated` |
| CI workflow changes | `uv run pytest tests/unit/tooling/test_validation_workflows.py -q` plus Make command equivalence |

## Test Placement

- `tests/unit/`: pure API, state, assets, events, and wrapper behavior, grouped into
  `api_lifecycle/`, `assets_media/`, `canvas_runtime/`, `ecs/`, `synth/`,
  `three_d/`, and `tooling/`.
- `tests/contracts/`: backend and renderer promises.
- `tests/golden/`: deterministic render comparisons.
- `tests/integration/`: end-to-end sketch behavior.
- `tests/benchmark/`: opt-in performance tests.
- `tests/stress/`: opt-in long-running resource lifecycle tests.
- `tests/helpers/`: shared fake canvas modules, renderer fakes, WebGL helpers,
  and other reusable test support that should not live under one specific test
  category. Canvas-runtime fakes live in `tests/helpers/canvas_runtime/`; ECS,
  synth, and WEBGL helpers remain reusable top-level helpers.
- `tests/fixtures/`: package-resource and file fixtures used by tests. Do not put
  test-only fixtures under `src/gummysnake`.

## Structure Guardrails

Run these after source-layout changes and before broad validation on refactor
branches:

```sh
uv run python scripts/source_size_audit.py
uv run python scripts/source_size_audit.py --check
uv run python scripts/structure_audit.py
# equivalent enforcement target:
make audit
```

`source_size_audit.py` reports implementation files over the 300-counted-line
review threshold while excluding import/export barrels. Its `--check` mode scans
all Python and Cargo-workspace production roots, including canvas, ECS, synth,
and acceleration crates, then fails on new or enlarged files above the reviewed
500-line enforcement policy. `structure_audit.py` catches confusing Python
module/package sibling patterns, source-package test fixtures, stale renamed
layout references, missing generated-output ignore policy, and undocumented or
stale Rust same-stem hubs, missing local Markdown links, stale current source-path code spans, and
unreviewed support-file prefix clusters across every workspace crate. Run `make assets-check` to
compile source-defined synth/FX assets into temporary outputs and verify packaged `.gss`/`.gsfx`
assets are current without modifying them. `impact_map_audit.py` validates the
maintained [source-to-test impact map](source_test_impact_map.md): every top-level
Python/Rust owner, category decision, named check path, command path, and Cargo
workspace owner must remain current. After `uv build --sdist`, run
`make verify-sdist SDIST_DIR=dist` to discover and verify the one generated
archive, including recursive local Cargo sources and Maturin-included assets. This
direct discovery command deliberately rejects a shared directory with zero or
multiple matching archives; use `make package-verify` for an isolated, repeatable
build-and-verify run.

## Distribution Contracts

`gummysnake` is a typed package: release wheels must contain
`gummysnake/py.typed`, `_canvas.pyi`, and `_accelerated.pyi`. The mandatory
canvas wheel must also contain a native `gummysnake.rust._canvas` extension.
The optional acceleration wheel is verified separately because it is not a
fallback for canvas, ECS, synth, or assets.

Use release-built wheels for the complete contract:

```sh
make build-rust WHEEL_DIR=dist/canvas
make build-accel ACCELERATED_WHEEL_DIR=dist/accelerated
make verify-wheel-accel WHEEL_DIR=dist/canvas ACCELERATED_WHEEL_DIR=dist/accelerated
```

The verifier inspects wheel members, compares every public native module
function’s symbol and runtime signature to its shipped `.pyi` file, then uses
`uv run --isolated` to type-check and execute a consumer installed from the
wheel. That consumer requires canvas ABI 18, ECS ABI 4, health checks, an
empty Rust ECS world, a headless frame, packaged synth/FX/sample lookup, and a
non-empty Rust-rendered WAV. A separate consumer blocks the native extension and
requires the clear rebuild-guidance capability error rather than a Python
fallback. Both consumers reject source-tree imports.

## Performance Benchmarks

Runtime performance checks live under `tests/benchmark/` and are skipped unless
explicitly requested. Shared subprocess execution, JSON parsing, and metric
summary helpers live in `tests/benchmark/benchmark_helpers.py`; add benchmark
suites to that helper instead of copying child-process boilerplate:

```sh
uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_api_overhead_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_image_pipeline_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_model_export_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_webgl_3d_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_ecs_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_ecs_spatial_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_ecs_ants_2d_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_ecs_scenarios_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_synth_offline_perf.py --run-benchmarks
```

The deterministic offline synth benchmark renders a fixed serialized plan with a
packaged sample and FX through the mandatory canvas/synth bridge. It asserts WAV
format, non-silence, and byte-identical repeated renders, while reporting local
render time without treating native playback as a wall-clock gate.

The canvas backend benchmarks require the `gummysnake.rust._canvas` runtime
module and run bounded native interactive windows, because interactive
presentation is the runtime performance acceptance path. Headless/offscreen
numbers are useful for export diagnostics, but they are not the canvas runtime
performance standard. Each run reports frames per second plus the canvas size,
pixel density, backend mode, Python version, platform, and renderer metrics.
The metrics payload includes command/draw counts, primitive and image batch
records, flush counts, largest coalesced batch sizes, vertex-buffer
allocations/uploads, texture uploads and cache hits, text cache hits/misses,
pixel readbacks/uploads, GPU region-effect passes, presented frame counts, and
CPU fallback counts. Every normal canvas benchmark scenario must average at
least 240 FPS. Recovered regression variants from epics 246-250 should keep
additional margin where practical: dense primitives around 320 FPS mean and
cached/transformed images, upload churn, sprite/text overlays, and mixed
text/pixel scenes around 300 FPS mean on the baseline machine class. High-count
primitive and sprite stress variants use a 60 FPS stress target for explicitly
named 10k/50k draw-count stress cases. The separate high-count primitive suite
runs 10k, 50k, and 100k static retained-batch scenes behind
`--run-high-count-benchmarks -k high_count`. A below-threshold failure is an
optimization signal, not a reason to loosen the benchmark.

Use the suite when changing renderer hot paths, image upload/cache behavior,
pixel readback/update behavior, text measurement, frame scheduling, or native
canvas packaging. The current scenarios cover sparse and dense primitive
drawing, compact line batches, mixed primitive batches, transformed image/sprite
batches, procedural fill-only primitive instances, retained static command-stream
replay, 10k/50k/100k primitive stress scenes, cached image drawing with default
linear and nearest sampling, 10k/50k sprite stress scenes, per-frame image upload
churn, blend modes, erasing, transformed images, text, 1k label overlays,
ordered cached-text atlas fallback, mixed sprite/text overlays, pixel
readback/upload, dirty-region pixel updates, no-op pixel upload skips, mixed
text/pixel readback work, a deterministic game-style scene, and software/retained
3D scenes.
The mixed text/pixel benchmark intentionally exercises readback/update
boundaries; keep bulk pixel mutations in Rust or a Rust/GPU region path instead
of reintroducing Python per-pixel loops into the measured hot path.

The API overhead microbenchmarks use a no-op renderer/backend and do not require
the canvas runtime. They report nanoseconds per call for global-mode,
object-oriented sketch, context-direct, `fast()` facade, and renderer-direct
paths so Python dispatch overhead can be compared separately from renderer
work. The `fast()` cases should remain below equivalent global-mode dispatch
for dense-loop operations.

The image pipeline benchmarks measure Rust-backed image-local operations such
as region copy, resize, mask, filter, get, and set, plus list-based,
bytes-based, and region-based pixel workflows. Use them when changing `Image`,
`CanvasImage`, `load_image()`, media frame conversion, `get()`, `set()`,
`load_pixels()`, `load_pixel_bytes()`, `update_pixels()`, or image cache
behavior.

The model export benchmark compares streaming OBJ/STL export against the legacy
list-building approach for large generated meshes. It asserts output sanity and
a fixed peak-memory budget instead of an FPS floor.

The WEBGL 3D benchmarks exercise the current Rust-backed 3D path for box,
sphere, textured plane, imported model, and repeated primitive scenes. They
cover Rust-owned model handles, retained GPU model buffers, GPU
transform/projection/depth/material pipelines, texture sampling, and fallback
software paths. They are frame-style benchmarks and keep the same 240 FPS
target; failures are expected optimization signals for the Rust 3D/GPU path or
its fallback boundaries.

The ECS benchmarks verify that hot systems use Rust physical plans rather than
Python fallback execution. Performance claims should show
`ecs_physical_system_runs` greater than zero and `ecs_udf_calls` equal to zero for
the hot path. The deterministic ant-colony scenario uses 10,000 seeded ants and
four compiled plans; its sketch presentation and benchmark measurement adapter
share `examples/support/ant_colony/`. Stable ECS scenario IDs and their subprocess
payloads live in `examples/09_performance/ecs_scenarios/` and
`tests/benchmark/test_ecs_scenarios_perf.py`; the old temporary paths are tested
forwarders only. Spatial ECS benchmarks additionally check candidate/exact row
counts and per-algorithm counters for generic `ecs.spatial` relations. Use
release-built `gummy_canvas` extensions for comparisons; debug extension builds can
make ECS and renderer numbers look dramatically slower.

Checked-in baseline snapshots live in `tests/benchmark/baselines/` as TOML.
Each baseline records the command, machine/configuration, commit, canvas size,
pixel density, backend mode, frame count or iteration count, and whether GPU
availability is known. Canvas baselines also record the required 240 FPS floor,
whether each captured scenario met it, and any documented margin target for
recovered variants. To compare an optimization branch, run the same command on
the same machine, compare each scenario's mean/min/max
against the matching baseline, and describe material changes as percentages. Do
not compare absolute FPS or nanosecond values across different machines, OS
versions, Python versions, build modes, or power/thermal states.

Do not edit baseline numbers upward to satisfy the target. Keep captured values
as measured and let benchmark assertions fail until the implementation reaches
the required floor.

## Resource Stress Tests

Long-running lifecycle checks live under `tests/stress/` and are skipped unless
explicitly requested:

```sh
make test-stress
```

Use `make release-candidate` for the documented release-built combination of
release smoke, normal/high-count benchmark gates, and stress tests.

Run these before releases and when changing canvas resize, shutdown, image
texture caching, text/font caching, pixel readback/upload, direct shape/clip
finalization, ECS spatial index lifecycle, or CPU/GPU fallback boundaries. The
current scenarios churn transient images, dynamic text, repeated pixel
readback/upload, repeated resize, repeated close/recreate, CPU fallback paths,
and ECS spatial storage/index state where those tests are enabled. They assert
cache/counter behavior and basic state consistency; they are not FPS benchmarks.

## Test Style

Prefer deterministic tests:

- Use bounded headless runs with `max_frames` for sketch behavior.
- Include pixel-sampling regressions for renderer ordering bugs, especially text
  before primitives/images followed by later text, primitives after text/images,
  and HiDPI-sensitive fallback paths.
- Use fake canvas modules or fake runtime objects for capability and event edge
  cases.
- Assert public behavior instead of private implementation details when the
  public behavior is stable.
- Use contract tests when multiple backend/renderer implementations would be
  expected to satisfy the same promise.
- Keep benchmark tests behind the explicit benchmark marker.
- Keep slow lifecycle churn behind the explicit stress marker.

Avoid tests that require manual native windows unless the behavior cannot be
reasonably covered headlessly.

## CI Layout

```mermaid
flowchart LR
    Push[push or pull request] --> Quality[quality]
    Push --> Rust[rust]
    Push --> Package[package]
    Push --> Coverage[coverage]

    Quality --> Python[Make quality, audits, Python tests, release smoke]
    Rust --> Workspace[Make Rust format, Clippy, direct crate tests]
    Package --> Archive[Make build and distribution verifier]
    Coverage --> Cov[pytest-cov XML artifact]
```

The shared Linux composite action provisions native dependencies for every
Ubuntu job. `quality` invokes the canonical format/static-analysis/audit/version/
asset/focused/full/smoke targets; `rust` invokes `make rust-check`; and
`package` invokes `make package-verify`. Coverage is reported in the job summary
and uploaded as `coverage-xml`.

Publish repeats those same validation gates, then builds and runs the installed
wheel smoke on each wheel's Linux, macOS Intel, macOS ARM, or Windows builder.
The optional manual publish `release_candidate` input invokes the documented
`make release-candidate` gate; benchmarks and stress checks are otherwise never
silently promoted into ordinary CI.

## Coverage Reporting

The coverage job intentionally reports coverage without enforcing a threshold.
That makes coverage visible without blocking unrelated maintenance work. Add a
threshold only after the project has agreed on a baseline and exclusion policy.

## Backlog TOML

If you edit backlog items, preserve the existing `priority` key spelling and
validate the files:

```sh
uv run python -c "from pathlib import Path; import tomllib; [tomllib.load(p.open('rb')) for p in sorted(Path('.scratch/backlog').glob('**/*.toml'))]; print('Backlog TOML parsed successfully')"
```
