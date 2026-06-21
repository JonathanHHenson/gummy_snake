# Build Capabilities

Use this matrix when validating local builds, wheels, and release candidates.

| Capability | Required? | Build surface | Runtime probe | Smoke command |
| --- | --- | --- | --- | --- |
| Canvas runtime | Required | `crates/gummy_canvas` PyO3 module `gummysnake.rust._canvas` | `gummysnake.rust.canvas.require_canvas_runtime()` checks health and canvas ABI, including Rust-managed asset classes such as `CanvasImage`, `CanvasModel3D`, `CanvasMesh3D`, and `CanvasSound` | `uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1` |
| Headless canvas | Required | `gummy_canvas` default headless mode | `CanvasBackend.capabilities.headless` | `uv run pytest tests/unit/test_rust_canvas.py` |
| Native windows and input | Optional/platform-dependent | SDL3-backed native runtime in `gummy_canvas` | `gummysnake.rust.canvas.canvas_native_window_available()` | `uv run python examples/01_getting_started/basic_shapes.py --interactive` |
| GPU renderer | Optional/platform-dependent | `wgpu` path in `gummy_canvas` | `gummysnake.rust.canvas.canvas_gpu_status()` and `CanvasBackend.gpu_status()` | `uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks -q -s` |
| Media helpers | Optional extra | Python package extra `media` | import/use media helpers | `uv sync --extra media --dev` plus media-specific examples |
| Optional acceleration | Optional | `crates/gummy_accel` PyO3 module `gummysnake.rust._accelerated` | `gummysnake.rust.is_acceleration_available()` | `uv run pytest tests/unit/test_rust_acceleration.py` |
| Software WEBGL path | Required for accepted `WEBGL` mode | Rust-backed software projection/rasterization plus canvas presentation | backend flags `three_d=True`, `software_three_d=True`, `native_three_d=False` | `uv run pytest tests/benchmark/test_webgl_3d_perf.py --run-benchmarks -q -s` |

## Compatibility Marker

`gummy_canvas` exposes `CANVAS_ABI_VERSION` and `canvas_abi_version()`. Python
validates this marker before returning the runtime module from
`require_canvas_runtime()`. Missing, malformed, or mismatched markers raise
`BackendCapabilityError` with rebuild guidance, because they usually mean a
stale local runtime module is being imported with a newer Python package.

Use the release build command when rebuilding locally:

```sh
uvx maturin develop --release --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
```

The older explicit `--module-name` / `--python-source` command is documented in
some workflows for compatibility with previous maturin versions, but the crate
metadata now carries that configuration.

The desktop interactive runtime uses SDL3 and builds SDL3 from source/static by
default via the Rust `sdl3` dependency. Local builds therefore do not require a
separately installed system SDL3 library, but first builds may take longer while
SDL3 is compiled.

## Failure Diagnostics

- Missing `gummysnake.rust._canvas`: rebuild or reinstall the required canvas runtime.
- ABI mismatch: rebuild the runtime module from the same checkout as the Python
  package.
- Health-check failure: rebuild the runtime module and inspect the original health
  check exception.
- Native window unavailable: bounded/headless rendering can still run; only
  interactive windows and native input are unavailable.
- GPU unavailable: headless CPU-backed rendering can continue, but native
  interactive presentation and GPU-accelerated drawing may be disabled or
  slower.
