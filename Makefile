.DEFAULT_GOAL := help

PYTHON := uv run python
PYTEST := uv run pytest
DIST_DIR ?= dist
SDIST_DIR ?= $(DIST_DIR)
WHEEL_DIR ?= $(DIST_DIR)
ACCELERATED_WHEEL_DIR ?= $(DIST_DIR)/accelerated
# `package-verify` creates one fresh child for each invocation below this
# ignored, tool-owned workspace. It must not inspect or remove shared dist/ files.
PACKAGE_VERIFY_ROOT := .scratch/package-verify
# Keep Maturin's wheel tag and all native build tools aligned with the macOS
# baseline enforced in .cargo/config.toml. It is harmless on non-macOS hosts.
MACOSX_DEPLOYMENT_TARGET := 26.0
export MACOSX_DEPLOYMENT_TARGET

.PHONY: help \
	format format-check lint typecheck basedpyright static-analysis \
	audit-report audit docs-path-check impact-map-audit repository-audits \
	test-focused test-unit test-contract test-integration test-golden test-full test \
	test-benchmarks test-benchmarks-high-count test-stress \
	smoke smoke-extended smoke-release \
	runtime-develop-release rust-format-check rust-lint rust-test rust-check \
	assets-check version-check bump-version \
	build build-rust build-accel verify-sdist verify-wheel verify-wheel-accel \
	wheel-smoke package-verify release-candidate check

help:
	@printf '%s\n' \
	  'Validation targets (all checks are non-mutating to tracked files):' \
	  '  make check                 Comprehensive local gate; requires a release canvas runtime.' \
	  '  make test-focused          Unit and contract suites for quick feedback.' \
	  '  make test-full             Full Python suite; benchmark and stress tests stay opt-in.' \
	  '  make rust-check            Format, Clippy, and direct tests for every Rust crate.' \
	  '  make package-verify        Build and verify archives in a private temporary workspace.' \
	  '  make release-candidate     Release runtime, all smoke tiers, benchmarks, and stress tests.' \
	  '  make format                Intentionally mutates source formatting.'

# Python quality gates
format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

lint:
	uv run ruff check .

typecheck:
	uv run mypy src

basedpyright:
	uv run basedpyright

static-analysis:
	$(PYTHON) scripts/static_analysis_audit.py
	$(MAKE) lint typecheck basedpyright

# Repository, documentation, and path audits
audit-report:
	$(PYTHON) scripts/source_size_audit.py

audit:
	$(PYTHON) scripts/source_size_audit.py --check
	$(PYTHON) scripts/structure_audit.py

docs-path-check:
	$(PYTHON) scripts/structure_audit.py

impact-map-audit:
	$(PYTHON) scripts/impact_map_audit.py

repository-audits: audit impact-map-audit

# Python tests. The full suite deliberately leaves benchmark and stress markers opt-in.
test-focused: test-unit test-contract

test-unit:
	$(PYTEST) tests/unit -q

test-contract:
	$(PYTEST) tests/contracts -q

test-integration:
	$(PYTEST) tests/integration -q

test-golden:
	$(PYTEST) tests/golden -q

test-full:
	$(PYTEST)

test: test-full

test-benchmarks:
	$(PYTEST) tests/benchmark --run-benchmarks -q -s

test-benchmarks-high-count:
	$(PYTEST) tests/benchmark/test_canvas_backend_perf.py --run-benchmarks --run-high-count-benchmarks -k high_count -q -s

test-stress:
	$(PYTEST) tests/stress --run-stress -q -s

# Catalog-defined cumulative smoke tiers
smoke:
	$(PYTHON) scripts/example_smoke.py --tier fast

smoke-extended:
	$(PYTHON) scripts/example_smoke.py --tier extended

smoke-release:
	$(PYTHON) scripts/example_smoke.py --tier release

# Mandatory canvas runtime and Rust workspace checks. Extension-module coverage
# validates the build configuration used by the published canvas and accel wheels.
runtime-develop-release:
	uvx maturin develop --release --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module

rust-format-check:
	cargo fmt --all -- --check

rust-lint:
	cargo clippy --workspace --all-targets -- -D warnings
	cargo clippy --manifest-path crates/gummy_canvas/Cargo.toml --all-targets --features extension-module -- -D warnings
	cargo clippy --manifest-path crates/gummy_accel/Cargo.toml --all-targets --features extension-module -- -D warnings

rust-test:
	cargo test --manifest-path crates/gummy_canvas/Cargo.toml
	cargo test --manifest-path crates/gummy_ecs/Cargo.toml
	cargo test --manifest-path crates/gummy_synth/Cargo.toml
	cargo test --manifest-path crates/gummy_accel/Cargo.toml

rust-check: rust-format-check rust-lint rust-test

# Version, assets, and distribution contracts. The verifier discovers exactly one
# matching archive in each supplied directory, so CI never relies on shell globs.
# `package-verify` supplies a fresh private directory; direct verifier targets retain
# their ambiguity rejection for callers that intentionally use a shared directory.
assets-check:
	$(PYTHON) scripts/compile_synth_assets.py --check

version-check:
	$(PYTHON) scripts/bump_version.py --check

bump-version:
	@test -n "$(VERSION)" || (echo "Usage: make bump-version VERSION=0.2.3|patch|minor|major"; exit 2)
	$(PYTHON) scripts/bump_version.py $(VERSION)

build:
	uv build --out-dir $(DIST_DIR)

build-rust:
	uvx maturin build --release --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module --out $(WHEEL_DIR)

build-accel:
	mkdir -p $(ACCELERATED_WHEEL_DIR)
	uvx maturin build --release --manifest-path crates/gummy_accel/Cargo.toml --features extension-module --out $(ACCELERATED_WHEEL_DIR)
	$(PYTHON) scripts/package_acceleration_wheel.py $(ACCELERATED_WHEEL_DIR)/gummy_accel-*.whl

verify-sdist:
	$(PYTHON) scripts/verify_distribution.py --sdist-dir $(SDIST_DIR)

verify-wheel:
	$(PYTHON) scripts/verify_distribution.py --wheel-dir $(WHEEL_DIR)

verify-wheel-accel:
	$(PYTHON) scripts/verify_distribution.py --wheel-dir $(WHEEL_DIR) --accelerated-wheel-dir $(ACCELERATED_WHEEL_DIR)

wheel-smoke: verify-wheel

package-verify:
	@set -eu; \
	mkdir -p "$(PACKAGE_VERIFY_ROOT)"; \
	package_verify_dir=$$(mktemp -d "$(PACKAGE_VERIFY_ROOT)/run.XXXXXX"); \
	trap 'rm -rf "$$package_verify_dir"' EXIT; \
	$(MAKE) build DIST_DIR="$$package_verify_dir"; \
	$(MAKE) verify-sdist SDIST_DIR="$$package_verify_dir"; \
	$(MAKE) verify-wheel WHEEL_DIR="$$package_verify_dir"

# This is intentionally opt-in: it uses release-built extensions and preserves
# the checked-in benchmark thresholds; it is not part of normal developer/PR CI.
release-candidate: runtime-develop-release smoke-release test-benchmarks test-benchmarks-high-count test-stress

# Comprehensive non-mutating local validation. It writes only ignored build
# artifacts (including package verification's private .scratch workspace) and
# requires the caller to install the release runtime first.
check: format-check static-analysis repository-audits version-check assets-check test-full smoke-release rust-check package-verify
