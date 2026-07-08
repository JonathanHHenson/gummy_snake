# Entity Component Systems

Gummy Snake exposes an ECS API through `gummysnake.ecs` plus global/object-mode
helpers on `gs` and `Sketch`. Components and resources are Python dataclasses;
Rust-executed plan systems are decorated functions that record a logical plan through context-managed build blocks and return `None`; runtime Python systems use `@ecs.system`.

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
- `iter_component_fields(ComponentType, *field_names, tags=())`

`get_entity()` and `iter_entities()` return `ecs.EntityView` objects:

```python
hero = gs.get_entity(Position, tags=["Hero"])
hero[Position].x += 4
hero.add_component(Tile(2, 2))
```

For dense draw loops that only need read-only component values, use
`iter_component_fields()` to read selected Rust-owned columns in one batch instead
of issuing one Python attribute lookup per field:

```python
draw_fast = gs.fast()
for x, y in gs.iter_component_fields(Position, "x", "y", tags=["Particle"]):
    draw_fast.circle(x, y, 3)
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
@ecs.system_plan
def accelerate(body: ecs.Query[Velocity], gravity: ecs.Res[Gravity]) -> None:
    body[Velocity].dy.increase_by(gravity[Gravity].y)
```

## Systems and query expressions

A Rust-executed system plan is a decorated build function. Type annotations are
mandatory. The function is called once when registered with query/resource/event
proxies and an active plan-build session. It records actions with field methods
and ECS context managers, then returns `None`.

```python
@ecs.system_plan
def move(entity: ecs.Query[Position, Velocity]) -> None:
    seconds = ecs.dt()
    entity[Position].x.increase_by(entity[Velocity].dx * seconds)
    entity[Position].y.increase_by(entity[Velocity].dy * seconds)
```

Returned `ecs.Action` trees are a migration error for Rust system plans. Replace
`return ecs.set(field, value)` with `field.set_to(value)`, replace
`return ecs.do_in_parallel(...)` with `@ecs.system_plan(parallel=True)` or
`with ecs.do(parallel=True):`, and replace chained `ecs.when(...).do(...)` with
`with ecs.conditional():` plus `with ecs.when(...):` branches.

Register systems with optional groups, group ordering, dependencies, and run
conditions:

```python
movement = gs.add_system(move, name="movement", group="simulation")
gs.add_system(collision, name="collision", group="simulation")
gs.add_system(ai, name="ai", group="gameplay", run_if=lambda: game_is_running)

gs.group("simulation", before=["draw"])
gs.group("gameplay", after=["input"], before=["draw"], enabled=True)
gs.order(["input", "simulation", "gameplay", "draw"])

gs.disable_system(movement)
gs.enable_system(movement)
gs.remove_system(movement)
```

Referencing a group auto-creates it; `gs.group()` is only needed when you want to
set group-level `before`, `after`, `enabled`, or `run_if` configuration. Group
names must be `snake_case` because plugin hooks are generated from the group
name. Systems without an explicit `group=` are placed in an implicit
`system_<system_name>` group. A system may also belong to multiple intersecting
groups by passing a sequence, for example `group=("draw", "draw_background")`.
The system still runs exactly once, but every group membership contributes
ordering constraints, group `enabled`/`run_if` checks, and generated plugin hooks.
Such memberships are valid only when the group orders agree; memberships in
mutually ordered groups or induced system-order cycles raise `SystemPlanError`.
Implicit groups may use system-level `before=[...]` or `after=[...]`; systems
that provide `group=` must order the groups with `gs.group()` or `gs.order()`
instead. Group dependencies are topologically sorted with stable tie-break
ordering, and systems with equivalent group constraints run in registration
order. Python `run_if` callbacks are evaluated once per frame/system on the
lifecycle path and are not per-row accelerated work.
Decorated systems expose `system.explain()` for a readable action-tree summary
that includes branch conditions, set-value expressions, canvas commands, and
spatial relation descriptors useful in tests and diagnostics.

Systems run every drawn frame after frame state is updated. The draw callback is
registered as a Python ECS system in the built-in `draw` group, and `@gs.draw` is
an alias-style convenience for `@ecs.system(group="draw", ...)`.
Plugins observe each group with generated lifecycle hooks named
`before_<group_name>(context)` and `after_<group_name>(context)`, such as
`before_simulation`, `after_simulation`, `before_draw`, and `after_draw`.

System plans are serialized into the Rust ECS physical executor automatically.
This includes field `set_to`/`increase_by`/`decrease_by`, serial and parallel
`ecs.do` blocks, `ecs.conditional()` branches, arithmetic/comparison/math
expressions, query/resource field reads and writes, `for_each` over list/event
sources, typed events, structural entity commands, `ecs.dt()`,
`ecs.key_is_down(...)`, `exists(...)`, grouped aggregates, change-detection
filters, query exclusions with `ecs.Without[...]`, spatial relation
aggregates/metadata, and canvas draw commands recorded through
`gummysnake.ecs.canvas`. Unsupported plan nodes raise `SystemPlanError` instead
of executing a Python fallback. Runtime Python work must be declared with
`@ecs.udf` or `@ecs.system`.

Use `from gummysnake.ecs import canvas as ca` in Rust-executed ECS system plans
when drawing should become part of the ECS logical plan. Supported `ca.*` calls
record canvas actions during system registration and are replayed by the Rust
executor. They are not runtime drawing aliases; Python ECS systems/UDFs and
`@gs.draw` callbacks should use the normal `gummysnake` drawing API instead.

```python
from gummysnake.ecs import canvas as ca


@ecs.system_plan(group=("draw", "draw_actors"))
def draw_bodies(body: ecs.Query[Position]) -> None:
    ca.no_stroke()
    ca.fill(255, 210, 80)
    ca.circle(body[Position].x, body[Position].y, 4)
```

### Typing helpers for system helpers

When extracting reusable helper functions for ECS systems, annotate lazy values
with the public proxy/expression types instead of falling back to `Any`:

```python
def speed(state: ecs.ComponentExpressionProxy) -> ecs.Expression:
    return (state.dx * state.dx + state.dy * state.dy).sqrt()


def steering_value(velocity: ecs.ComponentExpressionProxy) -> ecs.Expression:
    return velocity.dx.clamp(-4.0, 4.0)
```

For draw-side and Python UDF/system boundaries, use `ecs.EntityView` or
`ecs.Entity[T]` annotations. Mutable Python entity access must be declared with
`ecs.EntityMutation[T](...)` metadata on `@ecs.udf` or `@ecs.system`;
`ecs.MutEntity` is deprecated. `gs.FastDrawScope` is the public type for a local
`draw_fast = gs.fast()` binding in examples that mix ECS readback with dense
drawing.

## System build blocks and mutations

Writable field expressions expose mutation methods:

- `field.set_to(value)` records an assignment,
- `field.increase_by(amount)` records `field = field + amount`,
- `field.decrease_by(amount)` records `field = field - amount`.

Use `ecs.do` for nested serial/parallel blocks:

```python
@ecs.system_plan(parallel=True)
def integrate(body: ecs.Query[Position, Velocity]) -> None:
    body[Position].x.increase_by(body[Velocity].dx)
    body[Position].y.increase_by(body[Velocity].dy)


@ecs.system_plan
def serial_then_parallel(body: ecs.Query[Position, Velocity]) -> None:
    body[Velocity].dx.set_to(body[Velocity].dx * 0.98)
    with ecs.do(parallel=True):
        body[Position].x.increase_by(body[Velocity].dx)
        body[Position].y.increase_by(body[Velocity].dy)
```

Conditionals use branch context managers inside `ecs.conditional()`:

```python
@ecs.system_plan
def clamp_x(body: ecs.Query[Position], bounds: ecs.Res[Bounds]) -> None:
    with ecs.conditional():
        with ecs.when(body[Position].x < 0):
            body[Position].x.set_to(0)
        with ecs.when(body[Position].x > bounds[Bounds].width):
            body[Position].x.set_to(bounds[Bounds].width)
```

`ecs.conditional(parallel=True)` makes branch bodies parallel by default;
`ecs.when(..., parallel=...)` and `ecs.otherwise(parallel=...)` can override that
per branch. `ecs.otherwise()` is the final branch for rows that did not match
previous conditions.

`ecs.for_each(source)` builds deterministic loop bodies over typed event readers,
Python-UDF iterable sources, or list/vector field expressions:

```python
@ecs.system_plan
def sum_samples(entity: ecs.Query[Trail], counter: ecs.ResMut[Counter]) -> None:
    with ecs.for_each(entity[Trail].samples) as sample:
        counter[Counter].value.increase_by(sample)
```

Structural commands are available from `query.entity`: `add_component(...)`,
`remove_component(Component)`, `add_tag(tag)`, `remove_tag(tag)`, and `despawn()`.
They are broad structural writes and affect scheduling/conflict diagnostics.

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
with ecs.conditional():
    with ecs.when(hero_on_platform):
        platform.ctx[Velocity].dx.set_to(3.0)
    with ecs.otherwise():
        platform.ctx[Velocity].dx.set_to(0.0)
```

Use `ecs.exists(query).where(predicate)` when a condition only needs to know if a
matching row exists:

```python
has_target = ecs.exists(targets).where(targets[Position].x > actor[Position].x)
```

Use `ecs.Without[T]` or `ecs.Without[ecs.Tag[tag]]` to exclude components or tags
while keeping query matching Rust-owned:

```python
@ecs.system_plan
def wake_sleepers(sleeper: ecs.Query[Position, ecs.Without[Velocity]]) -> None:
    sleeper.entity.add_component(Velocity(0.0, -1.0))
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


@ecs.system_plan
def proximity(
    pickup: ecs.Query[ecs.Tag["Pickup"], Position, Glow],
    player: ecs.Query[ecs.Tag["Player"], Position],
) -> None:
    nearby = spatial.join(
        pickup,
        player,
        origin_position=spatial.point2(pickup[Position].x, pickup[Position].y),
        target_position=spatial.point2(player[Position].x, player[Position].y),
        radius=80.0,
        algorithm=spatial.HashGrid(cell_size=80.0),
        allow_fallback=False,
    )
    with ecs.conditional():
        with ecs.when(nearby.any()):
            pickup.ctx[Glow].active.set_to(True)
        with ecs.otherwise():
            pickup.ctx[Glow].active.set_to(False)
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
@ecs.system_plan
def wake_new_particles(particle: ecs.Query[Position, ecs.Added[Velocity]]) -> None:
    particle[Velocity].dy.set_to(-2.0)


@ecs.system_plan
def redraw_dirty(sprite: ecs.Query[Position, ecs.Changed[Position]]) -> None:
    sprite[Position].x.set_to(sprite[Position].x)
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


@ecs.system_plan
def hazards(writer: ecs.EventWriter[Damage]) -> None:
    writer.emit(Damage(3))


@ecs.system_plan
def apply_damage(reader: ecs.EventReader[Damage], health: ecs.ResMut[Health]) -> None:
    with ecs.for_each(reader) as event:
        health[Health].value.decrease_by(event.amount)
```

The global/object APIs also expose `emit_event(event)`, `read_events(EventType)`,
and `clear_events(EventType | None = None)` for callback-side integration.
Events are frame-stamped and recent queues are retained across the next ECS pass
so systems registered after a callback can consume callback-emitted events.

## Explicit Python systems

Use `@ecs.system` when a scheduled system must execute Python at runtime. Python
systems are scheduler barriers by default, materialize query rows as Rust-backed
`EntityView` objects, run with the GIL held, and are diagnosed separately from
Rust physical systems. They are never an implicit fallback for an invalid Rust
logical system.

```python
@ecs.system(
    mutations={"entities": {ecs.EntityMutation[Velocity](update=True)}},
)
def dampen(entities: ecs.Query[Velocity]) -> None:
    for entity in entities:
        entity[Velocity].dx *= 0.98
        entity[Velocity].dy *= 0.98
```

Use the same `EntityMutation[T]` metadata for Python UDF and Python-system entity
parameters so readers can see the intentional write/structural boundary.

## UDFs

`@ecs.udf_plan` declares a typed Rust-backed UDF plan: value parameters and
returns use `ecs.Expression[T]`, and execution requires a matching Rust registry
entry. Use `@ecs.udf` for explicit runtime Python escape hatches, side effects,
external APIs, or operations that are not yet expressible in the lazy ECS DSL.
Python UDF annotations are mandatory and may use `ecs.Vector[T]`, `ecs.Entity[T]`,
or iterable return types. They are flexible but have a performance cost and are
counted separately in diagnostics.

```python
@ecs.udf(mutations={"items": {ecs.EntityMutation[Velocity](update=True)}})
def boost(items: Iterable[ecs.Entity[Velocity]]) -> None:
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
