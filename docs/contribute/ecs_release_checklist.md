# ECS Release Checklist

Use this checklist when preparing a release that includes ECS runtime changes.

## Required validation

```sh
uv run ruff check .
uv run mypy src
uv run pytest
cargo test --manifest-path crates/gummy_ecs/Cargo.toml
cargo test --manifest-path crates/gummy_canvas/Cargo.toml
uv run python examples/10_ecs/firefly_constellation.py --headless --frames 1 --no-save
uv run python examples/10_ecs/crystal_moths.py --headless --frames 1 --no-save
uv run python examples/09_performance/boids_3d.py --headless --frames 1 --no-save
uv run pytest tests/benchmark/test_ecs_perf.py -q --run-benchmarks
uv run pytest tests/benchmark/test_ecs_spatial_perf.py -q --run-benchmarks
uv run pytest tests/stress/test_ecs_spatial_lifecycle_stress.py -q --run-stress
```

## Review points

- Confirm `gummysnake.rust.ecs.EXPECTED_ECS_ABI_VERSION` matches the Rust
  `ECS_ABI_VERSION` exported by `gummy_ecs` through `gummy_canvas`.
- Confirm public ECS exports in `src/gummysnake/__init__.py`,
  `src/gummysnake/api/ecs.py`, and `src/gummysnake/api/global_mode/__init__.py`
  are explicit and documented.
- Confirm `docs/reference/ecs.md`, `docs/contribute/ecs_architecture.md`,
  `docs/contribute/ecs_debugging.md`, `docs/contribute/runtime_diagnostics.md`,
  and `docs/contribute/build_capabilities.md` describe capabilities and fallback
  boundaries without claiming unsupported Rust physical execution paths.
- Capture or refresh opt-in benchmark baselines under `tests/benchmark/baselines/`
  when performance targets are being changed.
- Keep `.scratch/backlog/10*_ecs_*` statuses truthful: mark items done only after
  their Python API, Rust physical execution, examples, diagnostics, docs, and
  validation commands have all been implemented and verified.
