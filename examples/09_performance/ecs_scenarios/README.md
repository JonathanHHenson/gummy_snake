# ECS performance scenarios

These maintained scenarios exercise distinct ECS runtime boundaries as runnable,
bounded examples. Their stable IDs are the module stems:
`rust_2d_primitives_branching`, `python_systems_udfs_sprites`,
`structural_churn_tags_components`, `spatial_events_for_each_stress`, and
`webgl_3d_ecs_primitives_models`.

Run a bounded scenario:

```sh
uv run python examples/09_performance/ecs_scenarios/rust_2d_primitives_branching.py --headless --frames 1 --no-save
```

Run additional scenarios directly with `--headless --frames 1 --no-save` to use
them as bounded functional smoke paths. For performance investigation, use a
release-built canvas extension and inspect `ecs_diagnostics()` plus
`renderer_performance_counters()` after representative runs.
