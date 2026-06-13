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

## GitHub Actions publishing

The repository includes `p5_py/.github/workflows/publish.yml` for trusted publishing.

Behavior:

- manual runs via `workflow_dispatch` can publish to either `testpypi` or `pypi`
- pushing a tag matching `v*` publishes to PyPI automatically after the build and validation steps pass

The workflow:

1. installs dependencies with `uv`
2. runs `ruff`, `mypy`, `pytest`, and the headless example smoke test
3. builds the sdist and wheel with `uv build`
4. verifies the distributions with `twine check`
5. publishes with `pypa/gh-action-pypi-publish`

### Required one-time PyPI setup

Configure trusted publishing in both PyPI and TestPyPI before using the workflow.

Recommended publisher settings:

- owner: your GitHub user or organization
- repository: the repository that contains this workflow
- workflow name: `publish.yml`
- environment name: `pypi` for PyPI and `testpypi` for TestPyPI

### Suggested release flow

1. bump the version in `pyproject.toml`
2. update `CHANGELOG.md`
3. run the local validation commands when preparing the release
4. trigger the workflow manually against `testpypi`
5. verify install and metadata from TestPyPI
6. either trigger the workflow manually against `pypi` or push a `v*` tag
