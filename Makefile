lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

test-fast:
	uv run pytest tests/unit tests/contracts

test:
	uv run pytest

smoke:
	uv run python examples/basic_shapes.py --headless --frames 1

build:
	uv build

build-rust:
	uvx maturin build --release

build-accel:
	uvx maturin build --release --manifest-path crates/gummy_accel/Cargo.toml --module-name gummysnake.rust._accelerated --python-source src --features extension-module

version-check:
	uv run python scripts/bump_version.py --check

bump-version:
	@test -n "$(VERSION)" || (echo "Usage: make bump-version VERSION=0.2.3|patch|minor|major"; exit 2)
	uv run python scripts/bump_version.py $(VERSION)

check: lint typecheck test smoke version-check build
