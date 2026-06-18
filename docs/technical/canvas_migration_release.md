# Canvas Migration Release Plan

Epic 095 keeps `backend="canvas"` opt-in until the Rust `p5_canvas` path has
proved GPU rendering parity, native runtime stability, packaging reliability,
and representative performance wins.

The current default backend remains `pyglet`. Default selection is centralized in
`p5.backends.registry.select_default_backend()`. The selector may return
`canvas` only when `CANVAS_DEFAULT_PARITY_READY` is intentionally changed and
the installed extension reports:

- `p5.rust._canvas` is importable
- `canvas_gpu_available()` is true
- `canvas_native_window_available()` is true

Until then, automatic selection falls back to `pyglet`; explicit
`backend="headless"`, `backend="pillow"`, `backend="pyglet"`, and
`backend="canvas"` remain available.

## GPU Parity Checklist

Before changing the default backend, validate all of these areas against the
Pillow/headless and Pyglet reference paths:

- primitives: point, line, triangle, quad, rect, square, ellipse, circle, arc,
  paths, stroke caps/joins/weights, fill/stroke/no-fill/no-stroke
- transforms: push/pop, translate, rotate, scale, shear, nested transforms, and
  transformed image/text/primitives at non-integer pixel densities
- color/style: RGB/HSB/HSL conversion, alpha, background, clear, blend modes,
  erase/no-erase, and style stack restoration
- images and text: image upload/cache invalidation, source cropping,
  destination scaling, sampling modes, text metrics, text alignment, font
  loading fallback, and clipping
- pixels/export: `load_pixels()`, `update_pixels()`, `blend()`, `copy()`,
  `save_canvas()`, top-left RGBA orientation, and physical backing-buffer size
- HiDPI: logical `width()`/`height()`, physical dimensions, `pixel_density()`,
  `display_density()`, resize behavior, and readback/export at Retina scale
- events/runtime: setup/draw ordering, loop/no-loop/redraw, frame-rate
  scheduling, close handling, mouse move/drag/press/release/click/double-click,
  wheel, key press/release/type, and logical-coordinate normalization
- examples: existing headless/Pyglet examples still run, and Rust canvas
  examples run with both bounded `--frames` and interactive native windows
- packaging: source install without Rust still imports, canvas extension wheels
  build on supported platforms, and missing-extension errors mention the local
  maturin command plus fallback backends
- performance: representative primitive-heavy scenes are faster than the Pyglet
  interactive path and remain stable across repeated runs

Ordinary GPU frames must not maintain an eager full-canvas CPU mirror. CPU
readback or upload is acceptable only for explicit APIs such as `load_pixels()`,
`update_pixels()`, `save_canvas()`, parity tests, or features that still require
CPU compositing during migration. Avoid implicit readbacks during presentation
and avoid surface-present throttling that hides renderer regressions.

## CI Coverage

Baseline CI keeps running:

```sh
uv run ruff check .
uv run mypy src
uv run pytest
uv run python examples/basic_shapes.py --backend headless --frames 1
uv build
uvx maturin build --release
```

Canvas-specific CI now also covers:

```sh
cargo test --manifest-path crates/p5_canvas/Cargo.toml
uvx maturin build --release --manifest-path crates/p5_canvas/Cargo.toml --module-name p5.rust._canvas --python-source src --features extension-module
uvx maturin develop --release --manifest-path crates/p5_canvas/Cargo.toml --module-name p5.rust._canvas --python-source src --features extension-module
uv run pytest tests/unit/test_rust_canvas.py tests/contracts/test_canvas_backend.py tests/contracts/test_canvas_renderer_parity.py
```

The Python test suite also keeps fallback coverage for unavailable extensions.
GPU smoke tests that require a physical adapter or display should stay
platform-specific and opt-in until the CI environment is reliable.

## Examples And Smoke Tests

Use the existing examples during the migration window:

```sh
uv run python examples/basic_shapes.py --backend headless --frames 1
uv run python examples/basic_shapes.py --backend pyglet
uv run python examples/new_rust_backend/canvas_primitives.py --frames 1
uv run python examples/new_rust_backend/canvas_transforms_density.py --frames 1
uv run python examples/new_rust_backend/canvas_pixels_export.py --frames 1
uv run python examples/new_rust_backend/canvas_assets_text.py --frames 1
uv run python examples/new_rust_backend/canvas_blend_erase.py --frames 1
uv run python examples/new_rust_backend/canvas_asteroids.py --frames 1
```

After `canvas_native_window_available()` returns true on a supported desktop,
also smoke-test:

```sh
uv run python examples/new_rust_backend/canvas_primitives.py
uv run python examples/new_rust_backend/canvas_asteroids.py
```

Confirm native windows open, render, accept input, resize correctly, and close
without hanging.

## Benchmarks

Collect benchmark evidence before changing the default:

```sh
uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks
uv run pytest tests/benchmark/test_interactive_backend_perf.py --run-benchmarks -s
```

The headless canvas benchmark must execute the `asteroids`, `dense_primitives`,
and `sparse_primitives` variants without failures. The interactive benchmark
must show `canvas` faster than `pyglet` for the representative Asteroids scene
on supported desktop platforms. If the ratio fails, keep `canvas` opt-in,
record the platform, adapter, driver, command output, and suspected bottleneck,
then resolve the blocker before enabling the default gate.

## Retention And Rollback

Keep `headless`, `pillow`, and `pyglet` through at least one migration release
after `canvas` becomes the default.

- `headless` remains the deterministic Pillow reference for golden tests,
  non-interactive export, and environments without native GPU access.
- `pillow` remains an alias of `headless` unless a separate schema/release note
  deprecates it.
- `pyglet` remains the fallback interactive backend while canvas platform
  coverage matures.
- Release notes for any default flip must include benchmark evidence, known
  platform limitations, fallback instructions, and the one-line rollback:
  pass `backend="pyglet"` or set the default selector back to `pyglet`.

Do not remove or deprecate old backends until the project has a documented wheel
matrix, GPU adapter troubleshooting notes, and successful release-candidate
feedback from supported platforms.
