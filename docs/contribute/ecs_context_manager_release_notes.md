# ECS Context-Manager API Release Notes

This release changes ECS system authoring from returned `ecs.Action` trees to
context-managed plan building.

## Breaking authoring change

Rust-executed system plans return `None` and record work through the active
plan-build session:

```python
@ecs.system_plan
def move(entity: ecs.Query[Position, Velocity]) -> None:
    entity[Position].x.increase_by(entity[Velocity].dx)
    entity[Position].y.increase_by(entity[Velocity].dy)
```

Migration examples:

- `return ecs.set(field, value)` → `field.set_to(value)`
- `return ecs.do_in_parallel(...)` → `@ecs.system_plan(parallel=True)` or
  `with ecs.do(parallel=True): ...`
- `ecs.when(condition).do(...)` → `with ecs.conditional():` plus
  `with ecs.when(condition): ...`
- `ecs.for_each(source).do(...)` → `with ecs.for_each(source) as item: ...`
- `ecs.emit_event(writer, event)` → `writer.emit(event)`

Returning `ecs.Action`, `ecs.SystemPlan`, or any other non-`None` value from a
Rust-executed system raises `SystemPlanError` with migration guidance. Invalid
Rust logical systems do not fall back to Python execution.

## New and clarified APIs

- Writable field proxies expose `set_to`, `increase_by`, and `decrease_by`.
- `query.entity` exposes structural plan commands: `add_component`,
  `remove_component`, `add_tag`, `remove_tag`, and `despawn`.
- `ecs.conditional`, `ecs.when`, `ecs.otherwise`, `ecs.do`, and `ecs.for_each`
  provide block-structured plan authoring.
- `ecs.EventWriter[T].emit(event)` and `ecs.EventReader[T]` integrate typed event
  queues into Rust physical plans.
- `ecs.Without[T]` and `ecs.Without[ecs.Tag[tag]]` exclude components/tags from
  query matching.
- `@ecs.udf_plan` declares typed Rust-backed UDF plans with `ecs.Expression[T]`
  inputs/outputs. Use `@ecs.udf` for explicit Python escape hatches.
- `ecs.Vector[T]`, `ecs.EntityMutation[T](...)`, and `Query.as_iter(...)` are the
  public typing/metadata surfaces for explicit Python UDF and Python-system data
  exchange.
- `@ecs.system(queries=..., mutations=...)` is the explicit spelling for
  scheduled runtime Python systems. Python systems are scheduler barriers and are
  diagnosed separately from Rust physical systems.

## Diagnostics

Diagnostics distinguish Rust physical system runs, Python UDF calls, vector or
entity materialization boundaries, explicit Python-system calls/barriers, event
emit/read counts, structural commands, and ambiguity/strict-mode errors. Use
`ecs_diagnostics()` or `EcsWorld.diagnostics()` to inspect counters after bounded
runs.
