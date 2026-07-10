from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.expression_tools import ExpressionInput
from gummysnake.ecs.expressions import Expression, QueryProxy, ensure_expr
from gummysnake.ecs.spatial.config import (
    Dimensions,
    FallbackPolicy,
    PairPolicy,
    SpatialAlgorithm,
    _validate_positive_or_zero_finite,
)
from gummysnake.ecs.spatial.relation_model.aggregate_expression import SpatialAggregateExpression
from gummysnake.ecs.spatial.relation_model.metadata import (
    SpatialAabb,
    SpatialDeltaProxy,
    SpatialMetadataExpression,
    SpatialPoint,
)
from gummysnake.ecs.spatial.runtime import (
    _aabb_overlaps,
    _distance_sq,
    _entity_order_key,
    _get_or_build_index,
    _spatial_context_key,
)
from gummysnake.ecs.specs import QuerySpec
from gummysnake.ecs.value_types import EcsLiteralValue

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


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

    def where(self, predicate: ExpressionInput) -> SpatialRelation:
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

    def sum(self, value: ExpressionInput) -> SpatialAggregateExpression:
        """Build an expression containing the sum of a value over matched items.

        Args:
            value: ECS expression or Python value to evaluate for each matched item.

        Returns:
            A lazy aggregate expression for this relation.
        """

        return SpatialAggregateExpression("sum", self, ensure_expr(value))

    def min(
        self, value: ExpressionInput, *, default: EcsLiteralValue | None = None
    ) -> SpatialAggregateExpression:
        """Build an expression containing the smallest value over matched items.

        Args:
            value: ECS expression or Python value to evaluate for each matched item.
            default: Value to use when the relation has no matches.

        Returns:
            A lazy aggregate expression for this relation.
        """

        return SpatialAggregateExpression("min", self, ensure_expr(value), default)

    def max(
        self, value: ExpressionInput, *, default: EcsLiteralValue | None = None
    ) -> SpatialAggregateExpression:
        """Build an expression containing the largest value over matched items.

        Args:
            value: ECS expression or Python value to evaluate for each matched item.
            default: Value to use when the relation has no matches.

        Returns:
            A lazy aggregate expression for this relation.
        """

        return SpatialAggregateExpression("max", self, ensure_expr(value), default)

    def mean(
        self, value: ExpressionInput, *, default: EcsLiteralValue | None = None
    ) -> SpatialAggregateExpression:
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
