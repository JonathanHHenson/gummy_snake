# Testing and quality checks

`p5-py` uses `pytest`, `ruff`, and static typing checks.

## Install the development environment

```sh
uv sync --dev
```

## Common commands

Fast unit-focused pass:

```sh
uv run pytest tests/unit
```

Full test suite:

```sh
uv run pytest
```

Lint:

```sh
uv run ruff check .
```

Format:

```sh
uv run ruff format .
```

Type checking:

```sh
uv run mypy src
```

Headless rendering smoke test:

```sh
uv run python examples/basic_shapes.py --headless --frames 1
```

Package build smoke test:

```sh
uv build
```

Rust acceleration wheel smoke test:

```sh
uvx maturin build --release --manifest-path crates/p5_accel/Cargo.toml --module-name p5.rust._accelerated --python-source src --features extension-module
```

Rust canvas crate and wheel smoke tests:

```sh
cargo test --manifest-path crates/p5_canvas/Cargo.toml
uvx maturin build --release --manifest-path crates/p5_canvas/Cargo.toml --module-name p5.rust._canvas --python-source src --features extension-module
```

## Test layers

The repository uses these test layers:

- `tests/unit/` for focused API and state behavior
- `tests/contracts/` for backend and renderer contract expectations
- `tests/golden/` for deterministic reference renders
- `tests/parity/` for backend alias/parity expectations
- `tests/integration/` for end-to-end sketch behavior

Compatibility-focused tests currently live in `tests/unit/test_compatibility.py`.

## Test-writing guidelines

Prefer the smallest deterministic test that proves behavior.

Recommended approach:

1. start with unit tests for pure logic or API validation
2. use bounded `canvas` runs when pixel output or frame determinism matters
3. add contract tests for backend/renderer capability behavior
4. add golden tests only for stable representative rendering slices
5. add parity tests when two implementations or aliases should agree
6. keep integration tests focused on end-to-end user behavior

Avoid interactive/manual-only tests unless the behavior genuinely cannot be covered headlessly.
