# Build Capabilities

Use this matrix when validating local builds, wheels, and release candidates.

| Capability | Required? | Build surface | Runtime probe | Smoke command |
| --- | --- | --- | --- | --- |
| Canvas runtime | Required | `crates/gummy_canvas` PyO3 module `gummysnake.rust._canvas` | `gummysnake.rust.canvas.require_canvas_runtime()` checks health and canvas ABI, including Rust-managed asset classes such as `CanvasImage`, `CanvasModel3D`, `CanvasMesh3D`, and `CanvasSound` | `uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1` |
| Headless canvas | Required | `gummy_canvas` default headless mode | `CanvasBackend.capabilities.headless` | `uv run pytest tests/unit/canvas_runtime/test_rust_canvas.py` |
| Native windows and input | Optional/platform-dependent | SDL3-backed native runtime in `gummy_canvas` | `gummysnake.rust.canvas.canvas_native_window_available()` | `uv run python examples/01_getting_started/basic_shapes.py --interactive --frames 1 --no-save` |
| GPU renderer | Optional/platform-dependent | `wgpu` path in `gummy_canvas` | `gummysnake.rust.canvas.canvas_gpu_status()` and `CanvasBackend.gpu_status()` | `uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks -q -s` |
| Media helpers | Optional extra | Python package extra `media` | import/use media helpers | `uv sync --extra media --dev` plus media-specific examples |
| Optional acceleration | Optional | `crates/gummy_accel` PyO3 module `gummysnake.rust._accelerated` | `gummysnake.rust.is_acceleration_available()` | `uv run pytest tests/unit/canvas_runtime/test_rust_acceleration.py` |
| WEBGL path | Required for accepted `WEBGL` mode | Rust-owned model handles, fallback software 3D paths, and built-in retained GPU model pipelines when GPU drawing is available | backend flags `three_d=True`, `software_three_d=True`, `native_three_d=False`, `native_shaders=False` | `uv run pytest tests/benchmark/test_webgl_3d_perf.py --run-benchmarks -q -s` |
| ECS runtime | Required for ECS system storage and physical execution; only explicit Python UDF bodies execute outside Rust | `crates/gummy_ecs` linked into `crates/gummy_canvas`, exposed through `gummysnake.rust._canvas` | `gummysnake.rust.ecs.ecs_abi_version()` and `gummysnake.rust.ecs.require_ecs_runtime()` validate the ECS ABI and bridge classes | `cargo test --manifest-path crates/gummy_ecs/Cargo.toml` plus `uv run pytest tests/unit/ecs/test_ecs.py -q` |
| Synth runtime | Required for `gummysnake.synth` rendering, sample decoding, and FX execution | `crates/gummy_synth` linked into `crates/gummy_canvas`, exposed through `gummysnake.rust._canvas` | `gummysnake.rust.canvas.require_canvas_runtime()` validates the canvas ABI and synth bridge functions | `cargo test --manifest-path crates/gummy_synth/Cargo.toml` plus `uv run pytest tests/unit/synth/test_synth_tracks.py -q` |

## Compatibility Marker

`gummy_canvas` exposes `CANVAS_ABI_VERSION` / `canvas_abi_version()` for canvas
and linked synth APIs, plus `ecs_abi_version()` for the Rust ECS bridge. Python
validates native integer markers and health probes before returning runtime modules.
Missing, malformed, unhealthy, or mismatched runtimes raise `BackendCapabilityError`
with rebuild guidance, because they usually mean a stale local runtime module is
being imported with a newer Python package. See [Runtime contracts](runtime_contracts.md)
for the frozen ABI and no-fallback boundary.

Use the release build command when rebuilding locally:

```sh
uvx maturin develop --release --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
```

The older explicit `--module-name` / `--python-source` command is documented in
some workflows for compatibility with previous maturin versions, but the crate
metadata now carries that configuration.

## Wheel Release Contract

Gummy Snake publishes a typed package. Every canvas wheel must ship
`gummysnake/py.typed`, both native stub files (`_canvas.pyi` and
`_accelerated.pyi`), the mandatory native `_canvas` extension, and the Maturin
assets. `scripts/verify_distribution.py --wheel <canvas-wheel>` installs only
the wheel through an isolated `uv` consumer environment, requires canvas ABI 18
and ECS ABI 4, validates health checks, exercises an empty Rust ECS world and a
headless render, and renders a WAV using packaged synth/FX/sample assets. A
second isolated consumer deliberately blocks the native canvas import and
requires clear rebuild-guidance capability errors instead of any Python
renderer/ECS/synth fallback. It also compares every public native module
function name and runtime signature to the shipped stub.

`gummy_accel` is an optional independently built extension, not a canvas/ECS/
synth fallback. Provide its wheel with `--accelerated-wheel <wheel>` to compare
its `_accelerated.pyi` surface against the built extension too. See
[Testing and CI](testing.md#distribution-contracts) and the
[canonical validation matrix](validation.md) for release commands.

The desktop interactive runtime uses SDL3 and builds SDL3 from source/static by
 default via the Rust `sdl3` dependency. Local builds therefore do not require a
 separately installed system SDL3 library, but first builds may take longer while
 SDL3 is compiled. Keep SDL3 as the primary native interactive path unless a new
 windowing experiment is explicitly requested.

### macOS Wheel Deployment Baseline

Canvas wheels support macOS 26.0 and newer on both Intel and Apple Silicon.
The bundled SDL3 source uses macOS 26 availability checks; with a lower
compiler deployment target, Apple Clang emits `__isPlatformVersionAtLeast`.
PyO3 extension modules intentionally use dynamic symbol lookup for Python, so
that helper becomes an unresolved flat-namespace symbol at import time.

`.cargo/config.toml` forces `MACOSX_DEPLOYMENT_TARGET=26.0` for Cargo build
scripts and native dependencies, and passes the matching
`-mmacosx-version-min=26.0` Rust linker argument for both macOS targets.
`Makefile` and the macOS publish-wheel job export the same value before Maturin
selects the wheel tag. The configuration is also explicitly included in the
sdist so CMake-driven dependencies receive the same target when consumers build
from source. Do not replace this with an arbitrary lower target unless SDL3 and
the native-link strategy are changed together.

On macOS, `scripts/verify_distribution.py --wheel ...` inspects every native
extension's `LC_BUILD_VERSION` with `otool`, requires macOS 26.0, rejects an
undefined `isPlatformVersionAtLeast` helper, and then performs the normal
isolated installed-wheel contract. This makes deployment-target regressions fail
before release rather than skipping native smoke.

## Failure Diagnostics

- Missing `gummysnake.rust._canvas`: rebuild or reinstall the required canvas runtime.
- ABI mismatch: rebuild the runtime module from the same checkout as the Python
  package.
- Health-check failure: rebuild the runtime module and inspect the original health
  check exception.
- Native window unavailable: bounded/headless rendering can still run; only
  interactive SDL3 windows and native input are unavailable.
- GPU unavailable: headless CPU-backed rendering can continue, but native
  interactive presentation and GPU-accelerated drawing may be disabled or
  slower.
- WEBGL visual scale drift: verify GPU model matrix conversion keeps rotation
  scale-stable, and verify fallback projected logical coordinates are scaled by
  `pixel_density()` before direct GPU primitive submission.
- ECS ABI mismatch or missing `EcsWorld` / `EcsSpatialIndexRegistry`: rebuild the
  canvas extension so it links the current `gummy_ecs` crate.
