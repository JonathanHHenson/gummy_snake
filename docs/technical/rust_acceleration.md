# Rust acceleration

`p5-py` keeps Rust optional. The Python package must work without compiling any
native extension, and accelerated functions must have deterministic Python
fallbacks with parity tests.

## Current scope

The first accelerated targets are narrow, pure computational paths:

- `noise_3d`: the Perlin-style noise core used by `p5_py.core.random.noise()`.
- `exclusion_blend_rgb`: the packed RGB byte loop used by the Pillow renderer's
  `EXCLUSION` blend mode.

These were selected because sketches commonly call noise once per point or pixel,
and per-pixel blend/filter loops are easy to isolate from renderer and backend
state. Both targets are pure functions, so they are low-risk seams for optional
native acceleration.

## Layout

```text
crates/
  p5_accel/
    Cargo.toml
    src/lib.rs
src/p5_py/rust/
  __init__.py          # optional import, wrappers, Python fallbacks
  _accelerated.pyi     # type stub for the compiled extension
  benchmarks.py        # local timing helpers
```

The compiled extension module is named `p5_py.rust._accelerated`. Importing
`p5_py.rust` never requires the extension to exist.

## Local build

From the repository root, install the normal Python development environment:

```sh
uv sync --dev
```

Build the extension into the active environment with maturin:

```sh
uvx maturin develop --release
```

The `pyproject.toml` `[tool.maturin]` settings point maturin at
`crates/p5_accel/Cargo.toml` and install the extension as
`p5_py.rust._accelerated` under the `src` Python source tree.

You can confirm which implementation is active with:

```sh
uv run python -c "import p5_py.rust as r; print(r.health_check())"
```

Expected values are:

- `rust-accelerated` when the extension is importable.
- `python-fallback` when the extension is absent.

## Packaging commands

Build a Rust-backed wheel locally with:

```sh
uvx maturin build --release
```

The default pure-Python build remains hatchling-based, so users and CI jobs that
do not build Rust still receive the Python fallback behavior.

## Tests and parity checks

Run the Rust acceleration test slice with:

```sh
uv run pytest tests/unit/test_rust_acceleration.py
```

Run the full Python validation suite with:

```sh
uv run ruff check .
uv run pytest
```

If Rust is built, the same tests compare the extension results against the Python
reference implementations. Current parity expectations are an absolute tolerance
of `1e-12` for `noise_3d` and exact byte-for-byte equality for
`exclusion_blend_rgb`. If Rust is not built, the tests still verify the fallback
paths and strategy selection.

## Benchmarks

Run small local timing helpers with:

```sh
uv run python -m p5_py.rust.benchmarks
```

The benchmark output reports both the wrapper path and the explicit Python
fallback path. Treat the timings as local smoke/profiling data rather than stable
performance guarantees. When Rust is unavailable, the wrapper path is expected to
use the same Python fallback and should not show a meaningful speedup.
