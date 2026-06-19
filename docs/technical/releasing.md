# Releasing and packaging

This repository now builds `p5-py` as a mixed Python/Rust package with Maturin. Published wheels must include the required `p5.rust._canvas` extension because rendering, image assets, text, pixels, export, and native presentation are owned by the `p5_canvas` runtime.

Do not publish a pure-Python wheel for runtime releases: it installs successfully but fails later when APIs such as `load_image()` call into `p5.rust._canvas`.

## Release checklist

1. update version metadata with `make bump-version VERSION=patch|minor|major|X.Y.Z`
2. update `CHANGELOG.md`
3. run lint, typing, tests, version sync, and a canvas example smoke test
4. build the source distribution and platform wheels
5. inspect build artifacts and confirm each wheel contains `p5/rust/_canvas.*`
6. publish to TestPyPI first
7. verify a clean install from TestPyPI on at least one supported platform
8. publish to PyPI when the package is ready

## Validation commands

```sh
uv sync --dev
uvx maturin develop --release --manifest-path crates/p5_canvas/Cargo.toml
uv run ruff check .
uv run mypy src
uv run pytest
uv run python examples/basic_shapes.py --headless --frames 1
uv run python scripts/bump_version.py --check
cargo test --manifest-path crates/p5_canvas/Cargo.toml
uv build
python -m zipfile --list dist/*.whl
```

The wheel listing should include a platform-specific extension file similar to:

```text
p5/rust/_canvas.cpython-312-...
```

## Version bumping

Use the bump helper to keep the root package, Rust crates, and `uv.lock` editable package entry in sync:

```sh
make bump-version VERSION=patch
make bump-version VERSION=minor
make bump-version VERSION=major
make bump-version VERSION=0.3.0
```

Preview without writing files:

```sh
uv run python scripts/bump_version.py 0.3.0 --dry-run
```

Check that managed versions are synchronized:

```sh
make version-check
```

## Local build

```sh
uv build
```

The root `pyproject.toml` uses Maturin with:

- `manifest-path = "crates/p5_canvas/Cargo.toml"`
- `module-name = "p5.rust._canvas"`
- `python-source = "src"`

This produces a source distribution and a platform wheel for the local machine. The source distribution can build from source when Rust tooling is available, but PyPI releases should also provide prebuilt wheels for supported platforms.

## Platform wheels

The publishing workflow builds wheels for Linux x86_64, macOS x86_64, macOS arm64, and Windows x64. Add more targets as support broadens.

For manual platform builds, prefer Maturin and confirm the resulting wheel contains `_canvas`:

```sh
uvx maturin build --release --out dist
python -m zipfile --list dist/*.whl
```

Linux wheels published to PyPI should use a manylinux-compatible build. The GitHub Actions workflow uses `PyO3/maturin-action` for this.

## Publishing notes

Before publishing, confirm the repository license file and any project URLs that should appear in package metadata.

## GitHub Actions publishing

The repository includes `.github/workflows/publish.yml` for trusted publishing.

Behavior:

- manual runs via `workflow_dispatch` can publish to either `testpypi` or `pypi`
- pushing a tag matching `v*` publishes to PyPI automatically after the build and validation steps pass

The workflow:

1. validates the package with `ruff`, `mypy`, `pytest`, and the canvas example smoke test
2. builds one source distribution
3. builds platform wheels containing `p5.rust._canvas`
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

1. bump versions with `make bump-version VERSION=patch|minor|major|X.Y.Z`
2. update `CHANGELOG.md`
3. run the local validation commands when preparing the release
4. trigger the workflow manually against `testpypi`
5. verify install and metadata from TestPyPI
6. either trigger the workflow manually against `pypi` or push a `v*` tag
