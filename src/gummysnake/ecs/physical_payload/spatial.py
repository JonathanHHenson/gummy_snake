"""Spatial expression and relation serialization for ECS physical payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gummysnake.ecs.logical_plan.expressions import Expression
from gummysnake.ecs.physical_payload.helpers import spatial_bounds_values
from gummysnake.ecs.physical_payload.types import BridgeNode, PayloadState, PhysicalPlanUnsupported
from gummysnake.exceptions import SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.physical_payload.expressions import ExpressionSerializer
    from gummysnake.ecs.spatial import SpatialAabb, SpatialPoint, SpatialRelation


class SpatialSerializer:
    """Serialize spatial ECS relation objects into Rust bridge payload nodes."""

    def __init__(self, state: PayloadState, expressions: ExpressionSerializer) -> None:
        self.state = state
        self.expressions = expressions

    def serialize_spatial_expr(self, expr: Expression) -> int | None:
        """Serialize supported spatial expressions or return ``None`` for other expressions."""

        from gummysnake.ecs.spatial import SpatialAggregateExpression, SpatialMetadataExpression

        if isinstance(expr, SpatialMetadataExpression):
            node: BridgeNode = {
                "kind": "spatial_metadata",
                "relation": self.serialize_spatial_relation(expr.relation),
                "metadata": expr.kind,
            }
            if expr.axis is not None:
                node["axis"] = int(expr.axis)
            return self.state.add_expr(node)
        if isinstance(expr, SpatialAggregateExpression):
            aggregate_node: BridgeNode = {
                "kind": "spatial_aggregate",
                "aggregate": expr.kind,
                "relation": self.serialize_spatial_relation(expr.relation),
            }
            if expr.value is not None:
                aggregate_node["value"] = self.expressions.serialize_expr(expr.value)
            if expr.default is not None:
                aggregate_node["default"] = self.expressions.serialize_literal(expr.default)
            return self.state.add_expr(aggregate_node)
        return None

    def serialize_spatial_relation(self, relation: SpatialRelation) -> BridgeNode:
        """Serialize one spatial relation and register its origin/item queries."""

        self.state.register_query(relation.origin)
        self.state.register_query(relation.item)
        relation_id = relation.name or f"spatial_relation:{id(relation)}"
        origin_position = self.serialize_spatial_point(relation.origin_position)
        target_position = self.serialize_spatial_point(relation.target_position)
        target_bounds = (
            self.serialize_spatial_bounds(relation.target_bounds)
            if relation.target_bounds is not None
            else None
        )
        algorithm = self.serialize_spatial_algorithm(relation)
        node: BridgeNode = {
            "id": relation_id,
            "index_id": self.spatial_relation_index_id(
                relation, target_position, target_bounds, algorithm
            ),
            "origin_query": relation.origin.name,
            "item_query": relation.item.name,
            "origin_position": origin_position,
            "target_position": target_position,
            "algorithm": algorithm,
            "include_self": bool(relation.include_self),
            "pair_policy": relation.pair_policy,
        }
        if relation.radius is not None:
            node["radius"] = self.expressions.serialize_expr(relation.radius)
        if relation.origin_bounds is not None:
            node["origin_bounds"] = self.serialize_spatial_bounds(relation.origin_bounds)
        if target_bounds is not None:
            node["target_bounds"] = target_bounds
        if relation.exact_filter is not None:
            node["exact_filter"] = self.expressions.serialize_expr(relation.exact_filter)
        return node

    def spatial_relation_index_id(
        self,
        relation: SpatialRelation,
        target_position: list[int],
        target_bounds: BridgeNode | None,
        algorithm: BridgeNode,
    ) -> str:
        """Build the stable cache key for a serialized spatial relation index."""

        return (
            "spatial_index:"
            f"item={relation.item.name};"
            f"target_position={target_position!r};"
            f"target_bounds={target_bounds!r};"
            f"algorithm={algorithm!r}"
        )

    def serialize_spatial_point(self, point: SpatialPoint) -> list[int]:
        """Serialize all expressions that make up a spatial point."""

        return [self.expressions.serialize_expr(expr) for expr in point.expressions]

    def serialize_spatial_bounds(self, bounds: SpatialAabb) -> BridgeNode:
        """Serialize minimum and maximum points for an axis-aligned bounding box."""

        return {
            "minimum": self.serialize_spatial_point(bounds.min_point),
            "maximum": self.serialize_spatial_point(bounds.max_point),
        }

    def serialize_spatial_algorithm(self, relation: SpatialRelation) -> BridgeNode:
        """Serialize the configured spatial indexing algorithm for a relation."""

        from gummysnake.ecs.spatial import (
            Bounds2D,
            Bounds3D,
            HashGrid,
            HilbertCurve,
            Octree,
            Quadtree,
        )

        algorithm = relation.algorithm or HashGrid(1.0, dimensions=relation.dimensions)
        dimensions = getattr(algorithm, "dimensions", None) or relation.dimensions
        node: BridgeNode = {"kind": algorithm.kind, "dimensions": int(dimensions)}
        if isinstance(algorithm, HashGrid):
            node["cell_size"] = float(algorithm.cell_size)
        elif isinstance(algorithm, Quadtree | Octree):
            node["bounds"] = spatial_bounds_values(algorithm.bounds)
            node["capacity"] = int(algorithm.capacity)
        elif isinstance(algorithm, HilbertCurve):
            if not isinstance(algorithm.bounds, Bounds2D | Bounds3D):
                raise SystemPlanError("HilbertCurve bounds must be Bounds2D or Bounds3D.")
            node["bounds"] = spatial_bounds_values(algorithm.bounds)
            node["bits"] = int(algorithm.bits)
        else:
            raise PhysicalPlanUnsupported(
                f"spatial algorithm {type(algorithm).__name__} is not supported by "
                "Rust ECS execution"
            )
        return node
