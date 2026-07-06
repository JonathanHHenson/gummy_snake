"""Lazy spatial relation objects used by ECS system plans."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.expressions import Expression, QueryProxy, ensure_expr, replace_query
from gummysnake.ecs.specs import QuerySpec

from .config import (
    Dimensions,
    FallbackPolicy,
    PairPolicy,
    SpatialAlgorithm,
    _validate_positive_or_zero_finite,
)
from .runtime import (
    _aabb_overlaps,
    _distance_sq,
    _entity_order_key,
    _get_or_build_index,
    _spatial_context_key,
)

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


@dataclass(frozen=True)
class SpatialPoint:
    """Lazy 2D or 3D point built from ECS expressions.

    Args:
        expressions: Coordinate expressions for the point. Use ``point2()`` or ``point3()``
            in user code so dimensionality is checked consistently.
    """

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
    """Lazy axis-aligned bounding box built from ECS expressions.

    Args:
        min_point: Minimum corner of the box.
        max_point: Maximum corner of the box.
    """

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
    """Lazy ``x``, ``y``, and optional ``z`` deltas for a spatial relation."""

    relation: SpatialRelation

    @property
    def x(self) -> Expression:
        """Horizontal distance from the relation origin to the matched item."""

        return SpatialMetadataExpression(self.relation, "delta", 0)

    @property
    def y(self) -> Expression:
        """Vertical distance from the relation origin to the matched item."""

        return SpatialMetadataExpression(self.relation, "delta", 1)

    @property
    def z(self) -> Expression:
        """Depth distance for 3D spatial relations.

        Raises:
            AttributeError: If the relation is 2D.
        """

        if self.relation.dimensions != 3:
            raise AttributeError("2D spatial relations do not have delta.z.")
        return SpatialMetadataExpression(self.relation, "delta", 2)


@dataclass(frozen=True, eq=False)
class SpatialMetadataExpression(Expression):
    """Lazy expression for relation distance or delta metadata."""

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
    """Lazy relation that joins ECS query rows by position or bounds.

    Args:
        origin: Query rows that start the spatial lookup.
        item: Query rows that may match each origin row.
        origin_position: Point expression for the origin rows.
        target_position: Point expression for candidate item rows.
        radius: Optional distance limit for point-based relations.
        bounds: Reserved compatibility field for bounds-style relations.
        origin_bounds: Optional bounding box expression for origin rows.
        target_bounds: Optional bounding box expression for item rows.
        algorithm: Spatial index configuration used by the Rust executor.
        include_self: Whether an entity can match itself when origin and item queries overlap.
        allow_fallback: Whether legacy Python materialization is allowed at explicit Python
            boundaries.
        name: Optional human-readable name used in explain output and diagnostics.
        exact_filter: Additional lazy predicate applied after spatial candidate lookup.
        pair_policy: ``"all"`` for every ordered pair, or ``"unique_unordered"`` for each pair once.
    """

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
        """Per-axis distance from each origin row to each matched item row."""

        return SpatialDeltaProxy(self)

    @property
    def distance_sq(self) -> Expression:
        """Squared distance between each origin row and matched item row."""

        return SpatialMetadataExpression(self, "distance_sq")

    @property
    def distance(self) -> Expression:
        """Distance between each origin row and matched item row."""

        return SpatialMetadataExpression(self, "distance")

    def where(self, predicate: object) -> SpatialRelation:
        """Return a copy of the relation with an additional exact-match filter.

        Args:
            predicate: ECS expression evaluated after broad-phase spatial candidates are found.

        Returns:
            A new relation that keeps only candidates where ``predicate`` is true.
        """

        predicate_expr = ensure_expr(predicate)
        exact = predicate_expr if self.exact_filter is None else self.exact_filter & predicate_expr
        return replace(self, exact_filter=exact)

    def any(self) -> SpatialAggregateExpression:
        """Build an expression that is true when at least one item matches.

        Returns:
            A lazy boolean aggregate expression for this relation.
        """

        return SpatialAggregateExpression("any", self)

    def count(self) -> SpatialAggregateExpression:
        """Build an expression containing the number of matching items.

        Returns:
            A lazy integer aggregate expression for this relation.
        """

        return SpatialAggregateExpression("count", self)

    def sum(self, value: object) -> SpatialAggregateExpression:
        """Build an expression containing the sum of a value over matched items.

        Args:
            value: ECS expression or Python value to evaluate for each matched item.

        Returns:
            A lazy aggregate expression for this relation.
        """

        return SpatialAggregateExpression("sum", self, ensure_expr(value))

    def min(self, value: object, *, default: object | None = None) -> SpatialAggregateExpression:
        """Build an expression containing the smallest value over matched items.

        Args:
            value: ECS expression or Python value to evaluate for each matched item.
            default: Value to use when the relation has no matches.

        Returns:
            A lazy aggregate expression for this relation.
        """

        return SpatialAggregateExpression("min", self, ensure_expr(value), default)

    def max(self, value: object, *, default: object | None = None) -> SpatialAggregateExpression:
        """Build an expression containing the largest value over matched items.

        Args:
            value: ECS expression or Python value to evaluate for each matched item.
            default: Value to use when the relation has no matches.

        Returns:
            A lazy aggregate expression for this relation.
        """

        return SpatialAggregateExpression("max", self, ensure_expr(value), default)

    def mean(self, value: object, *, default: object | None = None) -> SpatialAggregateExpression:
        """Build an expression containing the average value over matched items.

        Args:
            value: ECS expression or Python value to evaluate for each matched item.
            default: Value to use when the relation has no matches.

        Returns:
            A lazy aggregate expression for this relation.
        """

        return SpatialAggregateExpression("mean", self, ensure_expr(value), default)

    def iter_contexts(self, ctx: dict[object, Any], world: EcsWorld) -> Iterable[dict[object, Any]]:
        if self.origin not in ctx:
            for origin in world.match_query(cast(QuerySpec, self.origin.spec)):
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
    """Lazy aggregate expression computed from a ``SpatialRelation``.

    Args:
        kind: Aggregate operation name, such as ``"count"`` or ``"mean"``.
        relation: Spatial relation to aggregate.
        value: Optional expression evaluated for each matched item.
        default: Optional value used when ``min``, ``max``, or ``mean`` has no matches.
    """

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
