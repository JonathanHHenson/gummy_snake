# Entity Component Systems

Gummy Snake exposes an ECS API through `gummysnake.ecs` plus global/object-mode
helpers on `gs` and `Sketch`. Components and resources are Python dataclasses;
systems are decorated functions that return an `ecs.Action` tree.

```python
from dataclasses import dataclass
from typing import Annotated

import gummysnake as gs
from gummysnake import ecs
from gummysnake.ecs import types as ecs_t


@dataclass
class Position:
    x: float
    y: float


@dataclass
class Tile:
    width: Annotated[int, ecs_t.UInt16]
    height: Annotated[int, ecs_t.UInt16]
```

## Components, entities, and tags

Create entities during setup or from callbacks:

```python
hero = gs.add_entity(Position(120, 160), Tile(1, 2), tags=["Hero"])
```

Common entity APIs are available in global mode and object mode:

- `add_entity(*components, tags=())`
- `despawn_entity(entity)`
- `add_component(entity, component)`
- `remove_component(entity, ComponentType)`
- `add_tag(entity, tag)` / `remove_tag(entity, tag)`
- `get_entity(*components, tags=())`
- `try_get_entity(*components, tags=())`
- `iter_entities(*components, tags=())`

`get_entity()` and `iter_entities()` return `ecs.EntityView` objects:

```python
hero = gs.get_entity(Position, tags=["Hero"])
hero[Position].x += 4
hero.add_component(Tile(2, 2))
```

Component/resource fields support scalar `bool`, `int`, `float`, and `str`.
Use `typing.Annotated` with `ecs.types` markers to request a specific Rust
storage type such as `ecs_t.UInt16` or `ecs_t.Float32`.

Vector and list storage markers are also available for ECS-owned component
columns:

```python
@dataclass
class Trail:
    samples: Annotated[list[float], ecs_t.List(ecs_t.Float64)]


@dataclass
class Velocity2D:
    xy: Annotated[tuple[float, float], ecs_t.Vec2F32]
```

Rust owns canonical entity, component, tag, resource, and event storage. Python
uses dataclasses to declare schemas and to pass initial component/resource values,
then exposes lightweight Rust-backed entity/resource views for draw code and UDF
boundaries. Normal ECS systems execute against Rust-owned columns without a
persistent Python data mirror.

## Resources

Resources are singleton dataclass values stored in the ECS world:

```python
@dataclass
class Gravity:
    y: float


gs.set_resource(Gravity(0.35))
gravity = gs.get_resource(Gravity)
gs.remove_resource(Gravity)
```

Systems receive resources with `ecs.Res[T]` or mutable resources with
`ecs.ResMut[T]`:

```python
@ecs.system
def accelerate(body: ecs.Query[Velocity], gravity: ecs.Res[Gravity]) -> ecs.Action:
    return ecs.set(body[Velocity].dy, body[Velocity].dy + gravity[Gravity].y)
```

## Systems and query expressions

A system is a decorated function. Type annotations are mandatory. The function is
called once when registered to build a lazy action plan; it must return an
`ecs.Action`, not a `SystemPlan`.

```python
@ecs.system
def move(entity: ecs.Query[Position, Velocity]) -> ecs.Action:
    return ecs.do_in_order(
        ecs.set(entity[Position].x, entity[Position].x + entity[Velocity].dx * ecs.dt()),
        ecs.set(entity[Position].y, entity[Position].y + entity[Velocity].dy * ecs.dt()),
    )
```

Register systems with optional deterministic order, dependencies, run
conditions, and system sets:

```python
movement = gs.add_system(move, order=10, name="movement")
gs.add_system(collision, after=[movement], name="collision")
gs.add_system(ai, run_if=lambda: game_is_running, set="gameplay")
gs.configure_system_set("gameplay", enabled=True, order=20)

gs.disable_system(movement)
gs.enable_system(movement)
gs.remove_system(movement)
```

`before=[...]` and `after=[...]` references are topologically sorted with stable
tie-break ordering; dependency cycles raise `SystemPlanError`. Python `run_if`
callbacks are evaluated once per frame/system on the lifecycle path and are not
per-row accelerated work. Decorated systems expose `system.explain()` for a
readable action-tree summary that includes branch conditions, set-value
expressions, and spatial relation descriptors useful in tests and diagnostics.

Systems run every drawn frame after frame state is updated and before plugin
`before_draw` hooks and user `draw()`. Plugins can observe ECS with
`before_ecs(context)` and `after_ecs(context)` hooks.

Non-UDF systems are serialized into the Rust ECS physical executor automatically.
This includes `set`, serial `do_in_order`, snapshot `do_in_parallel`,
`when`/`otherwise` chains, arithmetic/comparison/math expressions, query and
resource field reads/writes, `for_each` over list/event sources, `ecs.dt()`,
`ecs.key_is_down(...)`, `exists(...)`, grouped aggregates, change-detection
filters, typed ECS events, and spatial relation aggregates/metadata. Unsupported
non-UDF plan nodes raise `SystemPlanError` instead of executing a Python fallback.
Explicit `@ecs.udf` actions and iterable UDF sources are the only ECS plan pieces
that execute Python at runtime.

## Actions

Action builders include:

- `ecs.set(target_field, value)`
- `ecs.do(*actions)`
- `ecs.do_in_order(*actions)` for serial/read-after-write execution
- `ecs.do_in_parallel(*actions)` for independent action groups
- `ecs.when(condition).do(...)`
- `ecs.when(...).do(...).when(...).do(...).otherwise().do(...)`
- `ecs.for_each(udf_iterable_source).do(...)`
- `ecs.for_each(list_or_vector_field_expression).do(...)`

`otherwise()` is equivalent to a final `when(not previous_conditions)` branch.
A successive `.when(cond)` in a chain only sees rows that did not match earlier
branches.

Python `and`, `or`, `not`, and chained comparisons cannot be overloaded for lazy
plans. Use `&`, `|`, `~`, `ecs.all_of(...)`, or `ecs.any_of(...)`:

```python
inside = (left <= actor[Position].x) & (actor[Position].x <= right)
```

## Joins, grouping, and exists

Queries referenced by an expression automatically determine the join. If a
condition references two query parameters, it behaves like a cross join for that
condition:

```python
near = (hero[Position].x - platform[Position].x) < 20
```

When multiple joined rows write the same component field, deterministic
last-write-wins is used in non-strict mode and a runtime warning is emitted.
Use `group_by(query).any()` to collapse boolean joins to one row per group:

```python
hero_on_platform = near.group_by(platform).any()
return ecs.when(hero_on_platform).do(
    ecs.set(platform.ctx[Velocity].dx, 3.0)
).otherwise().do(
    ecs.set(platform.ctx[Velocity].dx, 0.0)
)
```

Use `ecs.exists(query).where(predicate)` when a condition only needs to know if a
matching row exists:

```python
has_target = ecs.exists(targets).where(targets[Position].x > actor[Position].x)
```

Grouped value aggregates are available on `group_by(query)` expressions:

```python
near = (hero[Position].x - platform[Position].x).abs() <= 50
count = near.group_by(platform).count()
sum_x = near.group_by(platform).sum(hero[Position].x)
mean_x = near.group_by(platform).mean(hero[Position].x, default=0.0)
```

Empty `count()` returns `0`, `any()` returns `False`, and `sum()` returns `0`.
`min()`, `max()`, and `mean()` require a `default=` for empty groups unless the
system guarantees at least one row.

## Spatial relations

Generic spatial APIs live under `ecs.spatial`. They build lazy relations over
query rows instead of sketch-specific kernels.

```python
from gummysnake.ecs import spatial


@ecs.system
def proximity(
    pickup: ecs.Query[ecs.Tag["Pickup"], Position, Glow],
    player: ecs.Query[ecs.Tag["Player"], Position],
) -> ecs.Action:
    nearby = spatial.join(
        pickup,
        player,
        origin_position=spatial.point2(pickup[Position].x, pickup[Position].y),
        target_position=spatial.point2(player[Position].x, player[Position].y),
        radius=80.0,
        algorithm=spatial.HashGrid(cell_size=80.0),
        allow_fallback=False,
    )
    return ecs.when(nearby.any()).do(
        ecs.set(pickup.ctx[Glow].active, True)
    ).otherwise().do(
        ecs.set(pickup.ctx[Glow].active, False)
    )
```

Implemented spatial relation features:

- `spatial.point2(...)` and `spatial.point3(...)` for scalar coordinate fields,
- `spatial.aabb2(...)` and `spatial.aabb3(...)` for dynamic bounding boxes,
- `spatial.neighbors(query, ...)` for self-neighbor relations,
- `spatial.join(origin, target, ...)` for two-query proximity/radius relations,
- `spatial.overlaps(origin, target, origin_bounds=..., target_bounds=...)` for
  AABB broad-phase collision relations,
- `spatial.HashGrid(cell_size=...)` for deterministic 2D/3D radius and AABB queries,
- relation metadata expressions: `.delta.x/y/z`, `.distance_sq`, `.distance`,
- relation filters via `.where(predicate)`,
- relation aggregates: `.any()`, `.count()`, `.sum(expr)`, `.min(...)`,
  `.max(...)`, and `.mean(...)`.

For self-collision broad phase, pass `pair_policy="unique_unordered"` to
`spatial.overlaps(...)` to emit each unordered pair once instead of both `A-B`
and `B-A`.

`Quadtree`, `Octree`, and `HilbertCurve` config objects are accepted as explicit
algorithm requests. Hash-grid, quadtree, octree, and 2D Hilbert-curve relations
serialize into the Rust physical executor behind a shared spatial trait, so
systems can switch algorithms without changing public query results. The legacy
`allow_fallback` keyword is accepted for source compatibility but scheduled ECS
systems do not use Python spatial fallback execution.

## Change detection

Use `ecs.Added[T]`, `ecs.Changed[T]`, and `ecs.Removed[T]` as query terms for
systems that should only run over entities whose component state changed in the
current ECS frame:

```python
@ecs.system
def wake_new_particles(particle: ecs.Query[Position, ecs.Added[Velocity]]) -> ecs.Action:
    return ecs.set(particle[Velocity].dy, -2.0)


@ecs.system
def redraw_dirty(sprite: ecs.Query[Position, ecs.Changed[Position]]) -> ecs.Action:
    return ecs.set(sprite[Position].x, sprite[Position].x)
```

`Added[T]` also counts as changed for `Changed[T]`. Direct Python mutations made
before the ECS phase are detected by comparing component snapshots at the start
of the frame. Mutations performed by earlier systems are visible to later ordered
systems in the same ECS phase. `Removed[T]` matches still-alive entities when the
component was removed during the frame and the query has enough remaining terms
to identify those entities, for example `ecs.Query[Position, ecs.Removed[Velocity]]`.
Despawned entities do not produce stale `EntityView` objects; use explicit typed
events when systems need to observe despawns.

## Typed events

Typed ECS events are dataclass or scalar values retained for deterministic
reader systems. Emit events from Python callbacks or systems:

```python
@dataclass
class Damage:
    amount: int


@ecs.system
def hazards(writer: ecs.EventWriter[Damage]) -> ecs.Action:
    return ecs.emit_event(writer, Damage(3))


@ecs.system
def apply_damage(reader: ecs.EventReader[Damage], health: ecs.ResMut[Health]) -> ecs.Action:
    event = ecs.for_each(reader)
    return event.do(
        ecs.set(health[Health].value, health[Health].value - event.item.amount)
    )
```

The global/object APIs also expose `emit_event(event)`, `read_events(EventType)`,
and `clear_events(EventType | None = None)` for callback-side integration.
Events are frame-stamped and recent queues are retained across the next ECS pass
so systems registered after a callback can consume callback-emitted events.

## UDFs

Python UDFs provide escape hatches for side effects, external APIs, or operations
that are not yet expressible in the lazy ECS DSL. Annotations are mandatory.
UDFs may be used as actions or iterable sources depending on their return type.
They are flexible but have a performance cost.

```python
@ecs.udf
def boost(items: Iterable[ecs.MutEntity[Velocity]]) -> None:
    for item in items:
        item[Velocity].dx *= 1.1


@ecs.udf
def names() -> Iterable[str]:
    return ("James", "Emily", "Janet")
```

## Strict mode and diagnostics

Configure strictness and warnings per sketch/world:

```python
gs.configure_ecs(strict=True)
gs.configure_ecs(warn_on_ambiguity=False)
```

Strict mode raises on ambiguous duplicate writes or overlapping
`do_in_parallel()` writes. With strict mode off, execution stays deterministic and
warnings can be suppressed while diagnostics still count the ambiguity. Diagnostics
also count schedule rebuilds, run-condition skips, Rust compiled physical plan
handles, Rust physical plan compiles and runs, UDF calls, spatial index builds,
candidate rows, exact rows, false positives, deduplicated spatial pairs, and
per-algorithm spatial index builds.

Inspect counters with:

```python
gs.ecs_diagnostics()
gs.reset_ecs_diagnostics()
```
