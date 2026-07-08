# Temporary ECS performance sketches

These sketches are runnable examples for reviewing ECS behavior and performance coverage before any of them are promoted into formal benchmark tests.

Run any sketch with the normal example flags, for example:

```sh
uv run python examples/11_temporary_perf_tests/rust_2d_primitives_branching.py --headless --frames 1 --no-save
```

Run the opt-in benchmark matrix with:

```sh
uv run pytest tests/benchmark/test_temporary_ecs_perf.py -q -s --run-benchmarks
```

Use `GUMMY_TEMP_ECS_BENCHMARK_FRAMES`, `GUMMY_TEMP_ECS_BENCHMARK_REPEATS`, and `GUMMY_TEMP_ECS_BENCHMARK_MODE=headless|interactive` to tune benchmark duration and mode.

## Coverage map

| Sketch | Main coverage |
| --- | --- |
| `rust_2d_primitives_branching.py` | Rust systems, Rust expression UDFs, `ecs.do`, `ecs.do(parallel=True)`, `@ecs.system(parallel=True)`, `ecs.conditional`, `ecs.when`, `ecs.otherwise`, `ecs.for_each`, typed events, and ECS canvas 2D primitive drawing. |
| `python_systems_udfs_sprites.py` | Explicit Python systems, Python UDF action boundaries, Python UDF iterable sources, normal `gs.*` drawing from a Python ECS system, and 2D sprite rendering. |
| `structural_churn_tags_components.py` | Rust structural ECS actions that add/remove tags and components for visual state changes, plus ECS canvas drawing that reacts to the changed structure. |
| `spatial_events_for_each_stress.py` | 2D spatial `neighbors`, `join`, `overlaps`, aggregate expressions, event emission/consumption, and event-reader `ecs.for_each`. |
| `webgl_3d_ecs_primitives_models.py` | Rust ECS 3D simulation with 3D spatial neighbors and Python WEBGL drawing of primitives plus a retained model. |

The ECS canvas import (`from gummysnake.ecs import canvas as ca`) is used only in Rust-executed ECS systems, where it records logical draw commands. Python systems use normal `gummysnake` drawing APIs.
