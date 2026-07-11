# ECS performance scenarios

These maintained scenarios exercise distinct ECS runtime boundaries and are both
runnable examples and opt-in benchmarks. Their stable IDs are the module stems:
`rust_2d_primitives_branching`, `python_systems_udfs_sprites`,
`structural_churn_tags_components`, `spatial_events_for_each_stress`, and
`webgl_3d_ecs_primitives_models`.

Run a bounded scenario:

```sh
uv run python examples/09_performance/ecs_scenarios/rust_2d_primitives_branching.py --headless --frames 1 --no-save
```

Run the release benchmark matrix:

```sh
uv run pytest tests/benchmark/test_ecs_scenarios_perf.py -q -s --run-benchmarks
```

Use `GUMMY_ECS_SCENARIOS_BENCHMARK_FRAMES`,
`GUMMY_ECS_SCENARIOS_BENCHMARK_REPEATS`, and
`GUMMY_ECS_SCENARIOS_BENCHMARK_MODE=headless|interactive` to tune measurement.
The former `examples/11_temporary_perf_tests/` and
`tests/benchmark/test_temporary_ecs_perf.py` paths remain forwarding entries for
this epic.
