# Benchmark scenario ownership

All benchmark comparisons require a `maturin develop --release` canvas extension
and a matching machine, OS, Python version, and build fingerprint. Baselines are
observations, not cross-machine targets.

| ID | Canonical command | Mode and gate | Reported contract |
| --- | --- | --- | --- |
| `canvas_backend_interactive_v1` | `uv run pytest tests/benchmark/test_canvas_backend_perf.py --run-benchmarks -q -s` | interactive, 240 FPS (documented stress gates excepted) | Existing JSON payload: variant, frame/build metadata, and flattened renderer diagnostics. |
| `ecs_performance_scenarios_v1` | `uv run pytest tests/benchmark/test_ecs_scenarios_perf.py --run-benchmarks -q -s` | configurable headless/interactive; 120 FPS | Stable scene ID, phase, frame/backend/machine metadata, and renderer/ECS diagnostics. |
| `ecs_ants_2d_voxel_colony_v1` | `uv run pytest tests/benchmark/test_ecs_ants_2d_perf.py --run-benchmarks -q -s` | Rust compiled-plan batch; 100 FPS | Deterministic world counts, physical-plan count/runs, zero UDF calls, and timing metadata. |

Compare only equivalent fields from matching release runs. The former temporary
ECS test and child paths, plus the legacy canvas child/scenes module paths, are
tested forwarding entries and are not implementation homes.
