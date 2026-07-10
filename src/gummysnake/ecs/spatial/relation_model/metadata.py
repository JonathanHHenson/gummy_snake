"""Lazy spatial relation objects used by ECS system plans."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.expression_tools import ExpressionInput
from gummysnake.ecs.expressions import Expression, QueryProxy, ensure_expr, replace_query
from gummysnake.ecs.specs import QuerySpec
from gummysnake.ecs.value_types import EcsLiteralValue

from gummysnake.ecs.spatial.config import (
    Dimensions,
    FallbackPolicy,
    PairPolicy,
    SpatialAlgorithm,
    _validate_positive_or_zero_finite,
)
from gummysnake.ecs.spatial.runtime import (
    _aabb_overlaps,
    _distance_sq,
    _entity_order_key,
    _get_or_build_index,
    _spatial_context_key,
)

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.spatial.relation_model.relation import SpatialRelation
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
