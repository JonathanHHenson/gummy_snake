# Testing and CI

Use the smallest checks that cover the change.

## Common Checks

```sh
uv run ruff check .
uv run mypy src
uv run pytest
uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1
cargo test --manifest-path crates/gummy_canvas/Cargo.toml
```

For coverage locally:

```sh
uv run pytest --cov=gummysnake --cov-report=term-missing --cov-report=xml
```

## Choosing The Right Check

Use focused checks while developing, then broaden before handing off:

| Change type | Minimum useful check |
| --- | --- |
| Pure Python API/state logic | targeted `uv run pytest tests/unit/...` |
| Public API export changes | unit tests plus `uv run mypy src` |
| Backend scheduling or capability behavior | `tests/contracts/` plus relevant unit tests |
| Renderer or pixel behavior | contract or integration test plus a headless smoke example |
| Rust canvas runtime behavior | `cargo test --manifest-path crates/gummy_canvas/Cargo.toml` plus Python wrapper tests |
| Software 3D or WEBGL path behavior | focused integration tests plus `tests/benchmark/test_webgl_3d_perf.py --run-benchmarks` when hot paths change |
| Long-running resource lifecycle behavior | `uv run pytest tests/stress --run-stress -q -s` |
| Documentation only | link/path review; no full test suite required unless commands changed |
| CI workflow changes | local command equivalence where practical |

## Test Placement

- `tests/unit/`: pure API, state, assets, events, and wrapper behavior.
- `tests/contracts/`: backend and renderer promises.
- `tests/golden/`: deterministic render comparisons.
- `tests/integration/`: end-to-end sketch behavior.
- `tests/benchmark/`: opt-in performance tests.
- `tests/stress/`: opt-in long-running resource lifecycle tests.

## Performance Benchmarks

Runtime performance checks live under `tests/benchmark/` and are skipped unless
explicitly requested:

```sh
uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_api_overhead_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_image_pipeline_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_model_export_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_webgl_3d_perf.py --run-benchmarks
```

The canvas backend benchmarks require the `gummysnake.rust._canvas` runtime module and run in
bounded headless mode, so they do not open a native window. Each run reports
frames per second plus the canvas size, pixel density, backend mode, Python
version, and platform. Every canvas benchmark scenario must average at least
240 FPS. A below-threshold failure is an optimization signal, not a reason to
loosen the benchmark.

Use the suite when changing renderer hot paths, image upload/cache behavior,
pixel readback/update behavior, text measurement, frame scheduling, or native
canvas packaging. The current scenarios cover sparse and dense primitive
drawing, cached image drawing with default linear and nearest sampling,
per-frame image upload churn, blend modes, erasing, transformed images, text,
pixel readback/upload, mixed text/pixel readback work, a deterministic game-style
scene, and a software 3D prototype scene.
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

The WEBGL 3D benchmarks exercise the current Rust-backed software 3D path for
box, sphere, textured plane, imported model, and repeated primitive scenes.
They cover Rust-owned model handles, projection/shading, textured rasterization,
and the direct GPU triangle path for untextured shaded faces. They are
frame-style benchmarks and keep the same 240 FPS target; failures are expected
optimization signals until native accelerated 3D or additional software
optimizations land.

Checked-in baseline snapshots live in `tests/benchmark/baselines/` as TOML.
Each baseline records the command, machine/configuration, commit, canvas size,
pixel density, backend mode, frame count or iteration count, and whether GPU
availability is known. Canvas baselines also record the required 240 FPS floor
and whether each captured scenario met it. To compare an optimization branch,
run the same command on the same machine, compare each scenario's mean/min/max
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
uv run pytest tests/stress --run-stress -q -s
```

Run these before releases and when changing canvas resize, shutdown, image
texture caching, text/font caching, pixel readback/upload, or CPU/GPU fallback
boundaries. The current scenarios churn transient images, dynamic text, repeated
pixel readback/upload, repeated resize, repeated close/recreate, and CPU
fallback paths. They assert cache/counter behavior and basic state consistency;
they are not FPS benchmarks.

## Test Style

Prefer deterministic tests:

- Use bounded headless runs with `max_frames` for sketch behavior.
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
    Push --> Coverage[coverage]
    Push --> BuildPython[build-python]
    Push --> BuildRust[build-rust]
    Push --> Canvas[canvas-runtime-python]

    Quality --> Lint[ruff]
    Quality --> Types[mypy]
    Quality --> Tests[pytest]
    Coverage --> Cov[pytest-cov XML artifact]
    BuildRust --> Cargo[cargo test]
```

Coverage is reported in the job summary and uploaded as `coverage-xml`.

## What Each CI Job Proves

- `quality`: verifies the main contributor path: install dev dependencies,
  build the required canvas runtime, lint, type check, version check, run the
  Python test suite, and smoke-test an example.
- `coverage`: runs the Python test suite with coverage instrumentation and
  uploads `coverage.xml`.
- `build-python`: verifies `uv build` can produce Python distributions.
- `build-rust`: verifies optional acceleration and required canvas Rust builds,
  and runs canvas crate tests.
- `canvas-runtime-python`: focuses on Python tests that require the canvas
  runtime.

If a job starts failing after a change, first identify which ownership boundary
the job covers. For example, a failure only in `build-rust` is usually a crate
or packaging issue, while a failure in `quality` after Rust builds successfully
is usually Python API, test, or example behavior.

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
