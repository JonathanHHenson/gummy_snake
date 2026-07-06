"""Python materialization helpers for ECS spatial relations.

Scheduled ECS systems use the Rust physical executor. These helpers support explicit
Python UDF/system boundaries that need to materialize spatial relations in Python.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.specs import QuerySpec
from gummysnake.exceptions import SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.runtime_views import Entity, EntityView
    from gummysnake.ecs.spatial.relations import SpatialRelation
    from gummysnake.ecs.world import EcsWorld


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
        for cell in _iter_cells(min_cell, max_cell):
            for record in self.grid.get(cell, ()):  # deterministic after final sort
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
    algorithm = relation.algorithm
    algorithm_kind = getattr(algorithm, "kind", "hash_grid")
    if algorithm is None or algorithm_kind == "hash_grid":
        cell_size = float(getattr(algorithm, "cell_size", 1.0))
        index: _SpatialIndex = _HashGridIndex(relation, records, cell_size)
        world._diagnostics["ecs_spatial_algorithm_hash_grid"] += 1
    else:
        raise SystemPlanError(
            f"Spatial algorithm {algorithm_kind!r} cannot be evaluated by the legacy Python "
            "spatial expression evaluator. Scheduled ECS systems execute this algorithm in Rust."
        )
    cache[key] = index
    world._diagnostics["ecs_spatial_indexes_registered"] = len(cache)
    world._diagnostics["ecs_spatial_indexes_built"] += 1
    world._diagnostics["ecs_spatial_index_rebuilds"] += 1
    return index


def _build_records(relation: SpatialRelation, world: EcsWorld) -> list[_SpatialRecord]:
    records: list[_SpatialRecord] = []
    for entity in world.match_query(cast(QuerySpec, relation.item.spec)):
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


def _distance_sq(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum((b - a) * (b - a) for a, b in zip(left, right, strict=True))


def _entity_order_key(entity: Entity) -> tuple[int, int, int]:
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
