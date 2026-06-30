"""Generic ECS spatial relation APIs.

The public API models spatial work as lazy relations over ECS query rows. Scheduled
systems serialize these relations into Rust physical plans, where hash-grid,
quadtree, octree, and 2D Hilbert backends execute behind the shared spatial trait.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, cast

from gummysnake.ecs.expressions import (
    Expression,
    QueryProxy,
    ensure_expr,
    replace_query,
)
from gummysnake.exceptions import SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld, EntityView

Dimensions = Literal[2, 3]
UpdatePolicy = Literal["auto", "rebuild_each_use", "rebuild_each_frame", "incremental"]
OutOfBoundsPolicy = Literal["overflow", "error"]
FallbackPolicy = bool | None
PairPolicy = Literal["all", "unique_unordered"]


@dataclass(frozen=True)
class Bounds2D:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        _validate_finite_bounds((self.min_x, self.min_y, self.max_x, self.max_y), 2)
        if self.min_x > self.max_x or self.min_y > self.max_y:
            raise ValueError("Bounds2D minimum values must be <= maximum values.")


@dataclass(frozen=True)
class Bounds3D:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def __post_init__(self) -> None:
        _validate_finite_bounds(
            (self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z), 3
        )
        if self.min_x > self.max_x or self.min_y > self.max_y or self.min_z > self.max_z:
            raise ValueError("Bounds3D minimum values must be <= maximum values.")


@dataclass(frozen=True)
class HashGrid:
    cell_size: float
    dimensions: Dimensions | None = None
    update: UpdatePolicy = "auto"

    kind: str = "hash_grid"

    def __post_init__(self) -> None:
        _validate_positive_finite(self.cell_size, "HashGrid.cell_size")
        _validate_dimensions(self.dimensions)
        _validate_update(self.update)


@dataclass(frozen=True)
class Quadtree:
    bounds: Bounds2D
    capacity: int = 16
    max_depth: int = 16
    update: UpdatePolicy = "auto"
    out_of_bounds: OutOfBoundsPolicy = "overflow"

    kind: str = "quadtree"
    dimensions: Dimensions = 2

    def __post_init__(self) -> None:
        _validate_tree_config(self.capacity, self.max_depth, self.update, self.out_of_bounds)


@dataclass(frozen=True)
class Octree:
    bounds: Bounds3D
    capacity: int = 16
    max_depth: int = 12
    update: UpdatePolicy = "auto"
    out_of_bounds: OutOfBoundsPolicy = "overflow"

    kind: str = "octree"
    dimensions: Dimensions = 3

    def __post_init__(self) -> None:
        _validate_tree_config(self.capacity, self.max_depth, self.update, self.out_of_bounds)


@dataclass(frozen=True)
class HilbertCurve:
    bounds: Bounds2D | Bounds3D
    bits: int = 16
    dimensions: Dimensions | None = None
    update: UpdatePolicy = "auto"
    out_of_bounds: OutOfBoundsPolicy = "overflow"

    kind: str = "hilbert_curve"

    def __post_init__(self) -> None:
        inferred = 2 if isinstance(self.bounds, Bounds2D) else 3
        dimensions = inferred if self.dimensions is None else self.dimensions
        _validate_dimensions(dimensions)
        if dimensions != inferred:
            raise ValueError("HilbertCurve dimensions must match the provided bounds object.")
        if self.bits <= 0 or self.bits > 31:
            raise ValueError("HilbertCurve.bits must be in the range 1..31.")
        _validate_update(self.update)
        if self.out_of_bounds not in {"overflow", "error"}:
            raise ValueError("out_of_bounds must be 'overflow' or 'error'.")


SpatialAlgorithm = HashGrid | Quadtree | Octree | HilbertCurve


@dataclass(frozen=True)
class SpatialPoint:
    expressions: tuple[Expression, ...]

    @property
    def dimensions(self) -> Dimensions:
        return cast(Dimensions, len(self.expressions))

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> tuple[float, ...]:
        values = tuple(float(expr.eval(ctx, world)) for expr in self.expressions)
        if any(not math.isfinite(value) for value in values):
            raise ValueError(f"Spatial point coordinates must be finite, got {values!r}.")
        return values

    def replace_query(self, old: QueryProxy, new: QueryProxy) -> SpatialPoint:
        return SpatialPoint(tuple(replace_query(expr, old, new) for expr in self.expressions))


@dataclass(frozen=True)
class SpatialAabb:
    min_point: SpatialPoint
    max_point: SpatialPoint

    @property
    def dimensions(self) -> Dimensions:
        return self.min_point.dimensions

    def eval(
        self, ctx: dict[object, Any], world: EcsWorld
    ) -> tuple[tuple[float, ...], tuple[float, ...]]:
        minimum = self.min_point.eval(ctx, world)
        maximum = self.max_point.eval(ctx, world)
        if len(minimum) != len(maximum):
            raise ValueError("Spatial AABB min/max dimensions must match.")
        if any(minimum[axis] > maximum[axis] for axis in range(len(minimum))):
            raise ValueError(
                f"Spatial AABB minimum values must be <= maximum values: {minimum!r}, {maximum!r}."
            )
        return minimum, maximum

    def center(self) -> SpatialPoint:
        return SpatialPoint(
            tuple(
                (low + high) / 2
                for low, high in zip(
                    self.min_point.expressions, self.max_point.expressions, strict=True
                )
            )
        )

    def replace_query(self, old: QueryProxy, new: QueryProxy) -> SpatialAabb:
        return SpatialAabb(
            self.min_point.replace_query(old, new), self.max_point.replace_query(old, new)
        )


@dataclass(frozen=True)
class SpatialDeltaProxy:
    relation: SpatialRelation

    @property
    def x(self) -> Expression:
        return SpatialMetadataExpression(self.relation, "delta", 0)

    @property
    def y(self) -> Expression:
        return SpatialMetadataExpression(self.relation, "delta", 1)

    @property
    def z(self) -> Expression:
        if self.relation.dimensions != 3:
            raise AttributeError("2D spatial relations do not have delta.z.")
        return SpatialMetadataExpression(self.relation, "delta", 2)


@dataclass(frozen=True, eq=False)
class SpatialMetadataExpression(Expression):
    relation: SpatialRelation
    kind: str
    axis: int | None = None

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        origin = self.relation.origin_position.eval(ctx, world)
        item = self.relation.target_position.eval(ctx, world)
        delta = tuple(
            item_value - origin_value for origin_value, item_value in zip(origin, item, strict=True)
        )
        if self.kind == "delta":
            if self.axis is None:
                return delta
            return delta[self.axis]
        distance_sq = sum(value * value for value in delta)
        if self.kind == "distance_sq":
            return distance_sq
        if self.kind == "distance":
            return math.sqrt(distance_sq)
        raise ValueError(f"Unknown spatial metadata expression {self.kind!r}.")

    def _ecs_outer_queries(self) -> set[QueryProxy]:
        return {self.relation.origin, self.relation.item}


@dataclass(frozen=True)
class SpatialRelation:
    origin: QueryProxy
    item: QueryProxy
    origin_position: SpatialPoint
    target_position: SpatialPoint
    radius: Expression | None = None
    bounds: object | None = None
    origin_bounds: SpatialAabb | None = None
    target_bounds: SpatialAabb | None = None
    algorithm: SpatialAlgorithm | None = None
    include_self: bool = False
    allow_fallback: FallbackPolicy = None
    name: str | None = None
    exact_filter: Expression | None = None
    pair_policy: PairPolicy = "all"

    @property
    def dimensions(self) -> Dimensions:
        return self.origin_position.dimensions

    @property
    def delta(self) -> SpatialDeltaProxy:
        return SpatialDeltaProxy(self)

    @property
    def distance_sq(self) -> Expression:
        return SpatialMetadataExpression(self, "distance_sq")

    @property
    def distance(self) -> Expression:
        return SpatialMetadataExpression(self, "distance")

    def where(self, predicate: object) -> SpatialRelation:
        predicate_expr = ensure_expr(predicate)
        exact = predicate_expr if self.exact_filter is None else self.exact_filter & predicate_expr
        return replace(self, exact_filter=exact)

    def any(self) -> SpatialAggregateExpression:
        return SpatialAggregateExpression("any", self)

    def count(self) -> SpatialAggregateExpression:
        return SpatialAggregateExpression("count", self)

    def sum(self, value: object) -> SpatialAggregateExpression:
        return SpatialAggregateExpression("sum", self, ensure_expr(value))

    def min(self, value: object, *, default: object | None = None) -> SpatialAggregateExpression:
        return SpatialAggregateExpression("min", self, ensure_expr(value), default)

    def max(self, value: object, *, default: object | None = None) -> SpatialAggregateExpression:
        return SpatialAggregateExpression("max", self, ensure_expr(value), default)

    def mean(self, value: object, *, default: object | None = None) -> SpatialAggregateExpression:
        return SpatialAggregateExpression("mean", self, ensure_expr(value), default)

    def iter_contexts(self, ctx: dict[object, Any], world: EcsWorld) -> Iterable[dict[object, Any]]:
        if self.origin not in ctx:
            for origin in world.match_query(cast(Any, self.origin.spec)):
                origin_ctx = dict(ctx)
                origin_ctx[self.origin] = origin
                yield from self.iter_contexts(origin_ctx, world)
            return

        epoch = getattr(world, "_spatial_epoch", 0)
        cache = getattr(world, "_spatial_relation_cache", None)
        if cache is None:
            cache = {}
            world._spatial_relation_cache = cache
        cache_key = (id(self), epoch, _spatial_context_key(ctx, self.origin, exclude=self.item))
        cached = cache.get(cache_key)
        if cached is not None:
            world._diagnostics["ecs_spatial_relation_cache_hits"] += 1
            for joined in cast(tuple[dict[object, Any], ...], cached):
                yield dict(joined)
            return
        world._diagnostics["ecs_spatial_relation_cache_misses"] += 1

        origin_entity = cast(Any, ctx[self.origin]).entity
        origin_point = self.origin_position.eval(ctx, world)
        radius = None if self.radius is None else float(self.radius.eval(ctx, world))
        if radius is not None:
            _validate_positive_or_zero_finite(radius, "spatial radius")
        origin_bounds = None if self.origin_bounds is None else self.origin_bounds.eval(ctx, world)
        index = _get_or_build_index(self, world)
        candidates = (
            index.query_bounds(origin_bounds)
            if origin_bounds is not None
            else index.query(origin_point, radius)
        )
        world._diagnostics["ecs_spatial_candidate_rows"] += len(candidates)
        exact_rows = 0
        materialized: list[dict[object, Any]] = []
        for record in candidates:
            item_entity = record.entity.entity
            if not self.include_self and item_entity == origin_entity:
                continue
            if self.pair_policy == "unique_unordered" and _entity_order_key(
                item_entity
            ) <= _entity_order_key(origin_entity):
                world._diagnostics["ecs_spatial_deduplicated_pairs"] += 1
                continue
            joined = dict(ctx)
            joined[self.item] = record.entity
            if radius is not None:
                distance_sq = _distance_sq(origin_point, record.point)
                if distance_sq > radius * radius:
                    world._diagnostics["ecs_spatial_false_positive_rows"] += 1
                    continue
            if origin_bounds is not None and (
                record.bounds is None or not _aabb_overlaps(origin_bounds, record.bounds)
            ):
                world._diagnostics["ecs_spatial_false_positive_rows"] += 1
                continue
            if self.exact_filter is not None and not bool(self.exact_filter.eval(joined, world)):
                continue
            exact_rows += 1
            materialized.append(joined)
        cache[cache_key] = tuple(dict(row) for row in materialized)
        for joined in materialized:
            yield dict(joined)
        world._diagnostics["ecs_spatial_exact_rows"] += exact_rows


@dataclass(frozen=True, eq=False)
class SpatialAggregateExpression(Expression):
    kind: str
    relation: SpatialRelation
    value: Expression | None = None
    default: object | None = None

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        epoch = getattr(world, "_spatial_epoch", 0)
        cache = getattr(world, "_spatial_aggregate_cache", None)
        if cache is None:
            cache = {}
            world._spatial_aggregate_cache = cache
        cache_key = (
            id(self),
            epoch,
            _spatial_context_key(ctx, self.relation.origin, exclude=self.relation.item),
        )
        if cache_key in cache:
            world._diagnostics["ecs_spatial_aggregate_cache_hits"] += 1
            return cache[cache_key]
        world._diagnostics["ecs_spatial_aggregate_cache_misses"] += 1

        values: list[Any] = []
        count = 0
        result: Any
        for joined in self.relation.iter_contexts(ctx, world):
            count += 1
            if self.kind == "any":
                cache[cache_key] = True
                return True
            if self.value is not None:
                values.append(self.value.eval(joined, world))
        if self.kind == "any":
            result = False
        elif self.kind == "count":
            result = count
        elif self.kind == "sum":
            result = sum(values) if values else 0
        elif self.kind == "min":
            if values:
                result = min(values)
            elif self.default is not None:
                result = self.default
            else:
                raise ValueError("Spatial min aggregate is empty and no default was provided.")
        elif self.kind == "max":
            if values:
                result = max(values)
            elif self.default is not None:
                result = self.default
            else:
                raise ValueError("Spatial max aggregate is empty and no default was provided.")
        elif self.kind == "mean":
            if values:
                result = sum(values) / len(values)
            elif self.default is not None:
                result = self.default
            else:
                raise ValueError("Spatial mean aggregate is empty and no default was provided.")
        else:
            raise ValueError(f"Unsupported spatial aggregate {self.kind!r}.")
        cache[cache_key] = result
        return result

    def _ecs_outer_queries(self) -> set[QueryProxy]:
        return {self.relation.origin}


@dataclass(frozen=True)
class _SpatialRecord:
    entity: EntityView
    point: tuple[float, ...]
    bounds: tuple[tuple[float, ...], tuple[float, ...]] | None = None


class _SpatialIndex:
    def __init__(self, relation: SpatialRelation, records: list[_SpatialRecord]) -> None:
        self.relation = relation
        self.records = sorted(records, key=lambda record: record.entity.entity.index)

    def query(self, origin_point: tuple[float, ...], radius: float | None) -> list[_SpatialRecord]:
        del origin_point, radius
        return list(self.records)

    def query_bounds(
        self, bounds: tuple[tuple[float, ...], tuple[float, ...]] | None
    ) -> list[_SpatialRecord]:
        del bounds
        return list(self.records)


class _HashGridIndex(_SpatialIndex):
    def __init__(
        self, relation: SpatialRelation, records: list[_SpatialRecord], cell_size: float
    ) -> None:
        super().__init__(relation, records)
        self.cell_size = cell_size
        self.grid: dict[tuple[int, ...], list[_SpatialRecord]] = defaultdict(list)
        for record in self.records:
            if record.bounds is None:
                self.grid[self._cell(record.point)].append(record)
                continue
            min_cell = self._cell(record.bounds[0])
            max_cell = self._cell(record.bounds[1])
            for cell in _iter_cells(min_cell, max_cell):
                self.grid[cell].append(record)

    def query(self, origin_point: tuple[float, ...], radius: float | None) -> list[_SpatialRecord]:
        if radius is None:
            return list(self.records)
        min_cell = self._cell(tuple(value - radius for value in origin_point))
        max_cell = self._cell(tuple(value + radius for value in origin_point))
        candidates: dict[int, _SpatialRecord] = {}
        ranges = [range(min_cell[axis], max_cell[axis] + 1) for axis in range(len(origin_point))]
        if len(ranges) == 2:
            for x in ranges[0]:
                for y in ranges[1]:
                    for record in self.grid.get((x, y), ()):  # deterministic after final sort
                        candidates[record.entity.entity.index] = record
        else:
            for x in ranges[0]:
                for y in ranges[1]:
                    for z in ranges[2]:
                        for record in self.grid.get(
                            (x, y, z), ()
                        ):  # deterministic after final sort
                            candidates[record.entity.entity.index] = record
        return [candidates[key] for key in sorted(candidates)]

    def query_bounds(
        self, bounds: tuple[tuple[float, ...], tuple[float, ...]] | None
    ) -> list[_SpatialRecord]:
        if bounds is None:
            return list(self.records)
        min_cell = self._cell(bounds[0])
        max_cell = self._cell(bounds[1])
        candidates: dict[int, _SpatialRecord] = {}
        for cell in _iter_cells(min_cell, max_cell):
            for record in self.grid.get(cell, ()):  # deterministic after final sort
                candidates[record.entity.entity.index] = record
        return [candidates[key] for key in sorted(candidates)]

    def _cell(self, point: tuple[float, ...]) -> tuple[int, ...]:
        return tuple(math.floor(value / self.cell_size) for value in point)


def point2(x: object, y: object) -> SpatialPoint:
    return SpatialPoint((ensure_expr(x), ensure_expr(y)))


def point3(x: object, y: object, z: object) -> SpatialPoint:
    return SpatialPoint((ensure_expr(x), ensure_expr(y), ensure_expr(z)))


def aabb2(min_x: object, min_y: object, max_x: object, max_y: object) -> SpatialAabb:
    return SpatialAabb(point2(min_x, min_y), point2(max_x, max_y))


def aabb3(
    min_x: object,
    min_y: object,
    min_z: object,
    max_x: object,
    max_y: object,
    max_z: object,
) -> SpatialAabb:
    return SpatialAabb(point3(min_x, min_y, min_z), point3(max_x, max_y, max_z))


def neighbors(
    query: object,
    *,
    position: SpatialPoint,
    radius: object,
    algorithm: SpatialAlgorithm | None = None,
    include_self: bool = False,
    allow_fallback: FallbackPolicy = None,
    name: str | None = None,
) -> SpatialRelation:
    origin = _as_query_proxy(query, "neighbors query")
    if not isinstance(position, SpatialPoint):
        raise SystemPlanError(
            "spatial.neighbors() position must be spatial.point2(...) or point3(...)."
        )
    item = QueryProxy(f"{origin.name}.item", origin.spec)
    relation = SpatialRelation(
        origin=origin,
        item=item,
        origin_position=position,
        target_position=position.replace_query(origin, item),
        radius=ensure_expr(radius),
        algorithm=algorithm or HashGrid(_default_cell_size(radius), dimensions=position.dimensions),
        include_self=include_self,
        allow_fallback=allow_fallback,
        name=name,
    )
    _validate_relation(relation)
    return relation


def join(
    origin: object,
    target: object,
    *,
    origin_position: SpatialPoint,
    target_position: SpatialPoint,
    radius: object | None = None,
    bounds: object | None = None,
    algorithm: SpatialAlgorithm | None = None,
    include_self: bool = False,
    allow_fallback: FallbackPolicy = None,
    name: str | None = None,
) -> SpatialRelation:
    origin_query = _as_query_proxy(origin, "join origin")
    target_query = _as_query_proxy(target, "join target")
    if not isinstance(origin_position, SpatialPoint) or not isinstance(
        target_position, SpatialPoint
    ):
        raise SystemPlanError(
            "spatial.join() positions must be spatial.point2(...) or point3(...)."
        )
    relation = SpatialRelation(
        origin=origin_query,
        item=target_query,
        origin_position=origin_position,
        target_position=target_position,
        radius=None if radius is None else ensure_expr(radius),
        bounds=bounds,
        algorithm=algorithm
        or HashGrid(_default_cell_size(radius), dimensions=origin_position.dimensions),
        include_self=include_self,
        allow_fallback=allow_fallback,
        name=name,
    )
    _validate_relation(relation)
    return relation


def overlaps(
    origin: object,
    target: object,
    *,
    origin_bounds: SpatialAabb,
    target_bounds: SpatialAabb,
    algorithm: SpatialAlgorithm | None = None,
    include_self: bool = False,
    pair_policy: PairPolicy = "all",
    allow_fallback: FallbackPolicy = None,
    name: str | None = None,
) -> SpatialRelation:
    origin_query = _as_query_proxy(origin, "overlaps origin")
    target_query = _as_query_proxy(target, "overlaps target")
    if not isinstance(origin_bounds, SpatialAabb) or not isinstance(target_bounds, SpatialAabb):
        raise SystemPlanError("spatial.overlaps() bounds must be spatial.aabb2(...) or aabb3(...).")
    if pair_policy not in {"all", "unique_unordered"}:
        raise SystemPlanError("spatial.overlaps() pair_policy must be 'all' or 'unique_unordered'.")
    relation = SpatialRelation(
        origin=origin_query,
        item=target_query,
        origin_position=origin_bounds.center(),
        target_position=target_bounds.center(),
        origin_bounds=origin_bounds,
        target_bounds=target_bounds,
        algorithm=algorithm or HashGrid(1.0, dimensions=origin_bounds.dimensions),
        include_self=include_self,
        allow_fallback=allow_fallback,
        name=name,
        pair_policy=pair_policy,
    )
    _validate_relation(relation)
    return relation


def _get_or_build_index(relation: SpatialRelation, world: EcsWorld) -> _SpatialIndex:
    epoch = getattr(world, "_spatial_epoch", 0)
    cache = getattr(world, "_spatial_index_cache", None)
    if cache is None:
        cache = {}
        world._spatial_index_cache = cache
    key = (
        relation.item,
        relation.target_position,
        relation.target_bounds,
        repr(relation.algorithm),
        epoch,
    )
    if key in cache:
        world._diagnostics["ecs_spatial_index_cache_hits"] += 1
        return cast(_SpatialIndex, cache[key])
    world._diagnostics["ecs_spatial_index_cache_misses"] += 1
    records = _build_records(relation, world)
    algorithm = relation.algorithm or HashGrid(1.0, dimensions=relation.dimensions)
    if isinstance(algorithm, HashGrid):
        index: _SpatialIndex = _HashGridIndex(relation, records, algorithm.cell_size)
        world._diagnostics["ecs_spatial_algorithm_hash_grid"] += 1
    else:
        raise SystemPlanError(
            f"Spatial algorithm {algorithm.kind!r} cannot be evaluated by the legacy Python "
            "spatial expression evaluator. Scheduled ECS systems execute this algorithm in Rust."
        )
    cache[key] = index
    world._diagnostics["ecs_spatial_indexes_registered"] = len(cache)
    world._diagnostics["ecs_spatial_indexes_built"] += 1
    world._diagnostics["ecs_spatial_index_rebuilds"] += 1
    return index


def _build_records(relation: SpatialRelation, world: EcsWorld) -> list[_SpatialRecord]:
    records: list[_SpatialRecord] = []
    for entity in world.match_query(cast(Any, relation.item.spec)):
        ctx: dict[object, Any] = {relation.item: entity}
        point = relation.target_position.eval(ctx, world)
        bounds = None if relation.target_bounds is None else relation.target_bounds.eval(ctx, world)
        records.append(_SpatialRecord(entity, point, bounds))
    return records


def _validate_relation(relation: SpatialRelation) -> None:
    if relation.origin_position.dimensions != relation.target_position.dimensions:
        raise SystemPlanError("Spatial origin and target point dimensions must match.")
    if (
        relation.origin_bounds is not None
        and relation.origin_bounds.dimensions != relation.dimensions
    ):
        raise SystemPlanError("Spatial origin bounds dimensions must match relation dimensions.")
    if (
        relation.target_bounds is not None
        and relation.target_bounds.dimensions != relation.dimensions
    ):
        raise SystemPlanError("Spatial target bounds dimensions must match relation dimensions.")
    algorithm = relation.algorithm
    if algorithm is None:
        return
    dimensions = getattr(algorithm, "dimensions", None)
    if dimensions is not None and dimensions != relation.dimensions:
        raise SystemPlanError(
            f"Spatial algorithm dimensions ({dimensions}) do not match relation dimensions "
            f"({relation.dimensions})."
        )


def _as_query_proxy(value: object, role: str) -> QueryProxy:
    if not isinstance(value, QueryProxy):
        raise SystemPlanError(f"spatial.{role} must be an ecs.Query system parameter.")
    return value


def _default_cell_size(radius: object | None) -> float:
    if isinstance(radius, int | float):
        _validate_positive_finite(float(radius), "spatial radius/cell_size")
        return float(radius) if float(radius) > 0 else 1.0
    return 1.0


def _distance_sq(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum((b - a) * (b - a) for a, b in zip(left, right, strict=True))


def _entity_order_key(entity: Any) -> tuple[int, int, int]:
    return (int(entity.world_id), int(entity.index), int(entity.generation))


def _spatial_context_key(
    ctx: dict[object, Any], primary: object, *, exclude: object | None = None
) -> tuple[object, ...]:
    primary_value = ctx.get(primary)
    if primary_value is not None and hasattr(primary_value, "entity"):
        entity = primary_value.entity
        simple = True
        for key, value in ctx.items():
            if key is primary or key is exclude or not hasattr(value, "entity"):
                continue
            simple = False
            break
        if simple:
            return (int(entity.world_id), int(entity.index), int(entity.generation))
    return _context_entity_key(ctx, exclude=exclude)


def _context_entity_key(
    ctx: dict[object, Any], *, exclude: object | None = None
) -> tuple[object, ...]:
    parts: list[tuple[int, int, int, int]] = []
    for key, value in ctx.items():
        if key is exclude or not hasattr(value, "entity"):
            continue
        entity = value.entity
        parts.append((id(key), int(entity.world_id), int(entity.index), int(entity.generation)))
    return tuple(sorted(parts))


def _aabb_overlaps(
    left: tuple[tuple[float, ...], tuple[float, ...]],
    right: tuple[tuple[float, ...], tuple[float, ...]],
) -> bool:
    left_min, left_max = left
    right_min, right_max = right
    return all(
        left_min[axis] <= right_max[axis] and right_min[axis] <= left_max[axis]
        for axis in range(len(left_min))
    )


def _iter_cells(min_cell: tuple[int, ...], max_cell: tuple[int, ...]) -> Iterable[tuple[int, ...]]:
    ranges = [range(min_cell[axis], max_cell[axis] + 1) for axis in range(len(min_cell))]
    if len(ranges) == 2:
        for x in ranges[0]:
            for y in ranges[1]:
                yield (x, y)
        return
    for x in ranges[0]:
        for y in ranges[1]:
            for z in ranges[2]:
                yield (x, y, z)


def _validate_dimensions(dimensions: int | None) -> None:
    if dimensions is not None and dimensions not in {2, 3}:
        raise ValueError("Spatial dimensions must be 2, 3, or None for inference.")


def _validate_update(update: str) -> None:
    if update not in {"auto", "rebuild_each_use", "rebuild_each_frame", "incremental"}:
        raise ValueError(
            "Spatial update must be 'auto', 'rebuild_each_use', 'rebuild_each_frame', "
            "or 'incremental'."
        )


def _validate_tree_config(capacity: int, max_depth: int, update: str, out_of_bounds: str) -> None:
    if capacity <= 0:
        raise ValueError("Spatial tree capacity must be positive.")
    if max_depth <= 0:
        raise ValueError("Spatial tree max_depth must be positive.")
    _validate_update(update)
    if out_of_bounds not in {"overflow", "error"}:
        raise ValueError("out_of_bounds must be 'overflow' or 'error'.")


def _validate_positive_finite(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive.")


def _validate_positive_or_zero_finite(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative.")


def _validate_finite_bounds(values: tuple[float, ...], dimensions: int) -> None:
    if len(values) != dimensions * 2 or any(not math.isfinite(value) for value in values):
        raise ValueError("Spatial bounds must contain finite min/max coordinates.")


__all__ = [
    "Bounds2D",
    "Bounds3D",
    "HashGrid",
    "HilbertCurve",
    "Octree",
    "Quadtree",
    "SpatialAabb",
    "SpatialAggregateExpression",
    "SpatialPoint",
    "SpatialRelation",
    "aabb2",
    "aabb3",
    "join",
    "neighbors",
    "overlaps",
    "point2",
    "point3",
]
