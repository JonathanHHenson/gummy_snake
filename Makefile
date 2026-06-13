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
	uv run python examples/basic_shapes.py --backend headless --frames 1

build:
	uv build

build-rust:
	uvx maturin build --release

check: lint typecheck test smoke build
