# ECS Debugging and Performance Triage

Use this guide when changing or diagnosing `gummysnake.ecs` behavior. The ECS public API is Pythonic; `@ecs.system_plan` functions execute in Rust physical storage/execution paths, while `@ecs.system` and `@ecs.udf` are explicit Python runtime boundaries.

## First checks

1. Reproduce with the smallest deterministic world possible.
2. Call `system.explain()` before running frames to inspect the logical action tree.
3. Run one bounded ECS frame and inspect `gs.ecs_diagnostics()` or `world.diagnostics()`.
4. If spatial relations are involved, check candidate/exact row counts, deduplicated pairs, and per-algorithm spatial index counters.
5. Turn on strict mode when investigating ambiguous writes:

   ```python
   gs.configure_ecs(strict=True)
   ```

Strict mode raises on duplicate write ambiguity and overlapping `do_in_parallel()` write sets. With strict mode off, behavior remains deterministic by using last-write-wins where duplicate writes occur; warnings can be suppressed with `warn_on_ambiguity=False`, but diagnostics still count the event.

## Explain output

`@ecs.system_plan` functions expose `explain()`:

```python
print(move_system.explain())
```

Use it to verify:

- the action tree shape (`do_in_order`, `do_in_parallel`, `when_chain`, `otherwise`, `for_each`),
- target fields and value expressions for `set_to(...)` and related field mutations,
- branch conditions for `ecs.when(...)`,
- UDF and event action boundaries,
- spatial relation descriptors, including relation name, algorithm, dimensions, origin/target query aliases, predicates, and pair policy.

The explain output is intended to be stable enough for tests and user debugging. Avoid exposing unstable Rust internal IDs in public explain strings unless they are explicitly labelled debug-only.

## Diagnostics counters

Common ECS counters:

| Counter | Meaning |
| --- | --- |
| `ecs_systems_registered` / `ecs_systems_enabled` | Current scheduler surface. |
| `ecs_schedule_rebuilds` | System registration, removal, enable state, dependencies, or group configuration changed schedule state. |
| `ecs_system_frame_runs` | ECS group phases run on drawn frames. |
| `ecs_rust_compiled_plans` | Rust-owned compiled physical plan handles currently cached by the world. |
| `ecs_rows_updated` | Component field writes performed by systems or APIs. |
| `ecs_structural_commands_applied` | Component/tag structural mutations. |
| `ecs_ambiguity_warnings` | Deterministic ambiguity detected in non-strict mode. |
| `ecs_ambiguity_warnings_suppressed` | Ambiguity logs suppressed while diagnostics stayed active. |
| `ecs_strict_mode_errors` | Ambiguity rejected in strict mode. |
| `ecs_udf_calls` | Python UDF action or iterable-source calls; these are flexibility escape hatches, not accelerated hot loops. |
| `ecs_python_system_calls` / `ecs_python_system_barriers` | Explicit `@ecs.system` runtime Python boundaries. |
| `ecs_python_system_entities_materialized` | Entity views materialized for explicit Python systems. |
| `ecs_change_detection_refreshes` | Change-tracking frame refreshes; component values remain Rust-owned and are not snapshotted in Python. |

Rust core/bridge counters include entity generation reuse, schema counts, query cache refreshes, matched archetypes/rows, resources, and event queue totals where the installed runtime exposes them.

## Spatial diagnostics

Spatial relation diagnostics are essential for performance triage:

| Counter | Meaning |
| --- | --- |
| `ecs_spatial_indexes_registered` | Active cached spatial index descriptors in the current world. |
| `ecs_spatial_indexes_built` / `ecs_spatial_index_rebuilds` | Index build count. Rebuilds are expected after movement or structural changes. |
| `ecs_spatial_index_cache_hits` / `ecs_spatial_index_cache_misses` | Index reuse within an ECS frame. |
| `ecs_spatial_relation_cache_hits` / `ecs_spatial_relation_cache_misses` | Relation result reuse for repeated aggregate expressions. |
| `ecs_spatial_aggregate_cache_hits` / `ecs_spatial_aggregate_cache_misses` | Aggregate result reuse. |
| `ecs_spatial_candidate_rows` | Broad-phase candidates before exact filtering. |
| `ecs_spatial_exact_rows` | Rows that passed exact filtering. |
| `ecs_spatial_false_positive_rows` | Candidates rejected by exact radius/AABB filtering. |
| `ecs_spatial_deduplicated_pairs` | Pairs skipped by `pair_policy="unique_unordered"`. |
| `ecs_spatial_algorithm_hash_grid` / `ecs_spatial_algorithm_quadtree` / `ecs_spatial_algorithm_octree` / `ecs_spatial_algorithm_hilbert_curve` | Rust spatial index builds by backend. |

For accelerated benchmark claims, assert `ecs_physical_system_runs` is non-zero, `ecs_udf_calls` is zero for the hot path, and spatial candidate/exact row counts match the intended relation shape.

The Rust spatial backend trait also exposes `SpatialMemoryStats` for backend-level tests and future diagnostics. Use it to check record/vector capacity reuse, bucket capacity, tree node counts, and overflow-list pressure when changing hash-grid, tree, or Hilbert implementations.

## Common failures

### Python boolean operators in plans

Python `and`, `or`, `not`, and chained comparisons cannot build lazy ECS expressions. Use bitwise operators:

```python
inside = (left <= actor[Position].x) & (actor[Position].x <= right)
```

A `TypeError` mentioning lazy query-plan values usually means a system used a Python boolean operator accidentally.

### Duplicate writes from joins

A condition that references multiple query parameters creates a join from context. If multiple joined rows write the same target, non-strict mode warns and uses deterministic last-write-wins. Prefer a grouped aggregate when the intent is one decision per entity:

```python
on_platform = contact_condition.group_by(platform).any()
with ecs.conditional(), ecs.when(on_platform):
    platform.ctx[Velocity].dx.set_to(3.0)
```

### Unsupported Rust physical nodes

Plan nodes should serialize to Rust physical execution. If a system plan raises `SystemPlanError` during compilation, inspect `system.explain()` and either express the operation with supported ECS actions/expressions or isolate the Python-only work in an explicit `@ecs.udf` or `@ecs.system` boundary.

### Stale entity handles

`Entity` values are generational handles. `StaleEntityError` means the entity was despawned, reused, or belongs to a different world. Prefer storing tags/components or re-querying by component/tag when data can outlive a frame.

### UDF performance

`@ecs.udf` is intentionally flexible and may perform side effects or call external APIs. It executes Python code and should not be used to claim Rust acceleration. If a UDF is doing pure component math in a hot loop, consider expressing it with ECS actions, resources, events, `for_each`, or a generic spatial relation.

## Validation commands

For ECS changes, start focused and then broaden:

```sh
uv run ruff check src/gummysnake/ecs tests/unit/test_ecs.py
uv run mypy src/gummysnake/ecs
uv run pytest tests/unit/test_ecs.py -q
cargo test --manifest-path crates/gummy_ecs/Cargo.toml
cargo test --manifest-path crates/gummy_canvas/Cargo.toml
uv run pytest tests/benchmark/test_ecs_perf.py -q --run-benchmarks
uv run pytest tests/stress/test_ecs_spatial_lifecycle_stress.py -q --run-stress
```

Run `uv run pytest` and the ECS release checklist before handoff when public API, docs, examples, or bridge code changed.
