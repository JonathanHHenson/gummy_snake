# Releasing and packaging

This repository uses a hatchling-based pure-Python build by default, with optional `maturin` commands for Rust-backed wheels when the extension is enabled.

## Release checklist

1. update version metadata in `pyproject.toml`
2. update `CHANGELOG.md`
3. run lint, typing, tests, and a headless example smoke test
4. build pure-Python distributions
5. optionally build Rust-backed wheels
6. inspect build artifacts
7. publish when the project is ready

## Validation commands

```sh
uv sync --dev
uv run ruff check .
uv run mypy src
uv run pytest
uv run python examples/basic_shapes.py --backend headless --frames 1
uv build
uvx maturin build --release
```

## Pure-Python build

```sh
uv build
```

This should produce an sdist and wheel using the default hatchling configuration.

## Optional Rust-backed wheel

```sh
uvx maturin build --release
```

The package must remain usable without the compiled extension. Rust acceleration is optional and should preserve Python fallback behavior.

## Publishing notes

Before the first public release, confirm the repository license file and any project URLs that should appear in package metadata.
