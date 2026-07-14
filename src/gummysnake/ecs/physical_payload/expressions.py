"""Expression serialization for ECS physical payloads."""

from __future__ import annotations

from typing import cast

from gummysnake.ecs.logical_plan.actions import LoopItem, UdfCallExpression
from gummysnake.ecs.logical_plan.expressions import (
    AttributeExpression,
    BinaryExpression,
    DeltatimeExpression,
    EntityExpression,
    ExistsExpression,
    Expression,
    FieldExpression,
    FunctionExpression,
    GroupedAnyExpression,
    GroupedValueAggregateExpression,
    KeyDownExpression,
    LiteralExpression,
    QueryProxy,
    ResourceProxy,
    UnaryExpression,
)
from gummysnake.ecs.physical_payload.helpers import bridge_literal_value, key_code, schema_name
from gummysnake.ecs.physical_payload.spatial import SpatialSerializer
from gummysnake.ecs.physical_payload.types import (
    BridgeLiteral,
    BridgeNode,
    PayloadState,
    PhysicalPlanUnsupported,
)
from gummysnake.ecs.value_types import EcsLiteralValue
from gummysnake.exceptions import SystemPlanError


class ExpressionSerializer:
    """Serialize lazy ECS expression objects into Rust bridge expression nodes."""

    def __init__(self, state: PayloadState) -> None:
        self.state = state
        self.spatial = SpatialSerializer(state, self)

    def serialize_expr(self, expr: Expression) -> int:
        """Serialize an expression once and reuse its bridge index on later references."""

        cached = self.state.expr_indices.get(id(expr))
        if cached is not None:
            return cached
        index = self._serialize_expr_uncached(expr)
        self.state.expr_indices[id(expr)] = index
        return index

    def _serialize_expr_uncached(self, expr: Expression) -> int:
        if isinstance(expr, LiteralExpression):
            return self.serialize_literal(expr.value)
        if isinstance(expr, LoopItem):
            return self._serialize_loop_item(expr)
        if isinstance(expr, FieldExpression):
            field_index = self._serialize_field_expr(expr)
            if field_index is not None:
                return field_index
        if isinstance(expr, AttributeExpression):
            return self.state.add_expr(
                {
                    "kind": "attribute",
                    "input": self.serialize_expr(expr.base),
                    "attribute": expr.attribute,
                }
            )
        if isinstance(expr, UnaryExpression):
            return self.state.add_expr(
                {"kind": "unary", "op": expr.op, "input": self.serialize_expr(expr.operand)}
            )
        if isinstance(expr, BinaryExpression):
            return self.serialize_binary_expr(expr.op, expr.left, expr.right)
        if isinstance(expr, FunctionExpression):
            return self.serialize_function_expr(expr)
        if isinstance(expr, UdfCallExpression):
            raise PhysicalPlanUnsupported(
                f"Rust-backed UDF {expr.definition.function.__name__!r} has no registered "
                "Rust executor"
            )
        if isinstance(expr, DeltatimeExpression):
            return self.state.add_expr({"kind": "input_state", "name": "dt"})
        if isinstance(expr, KeyDownExpression):
            return self.state.add_expr(
                {"kind": "input_state", "name": "key_down", "code": key_code(expr.key)}
            )
        if isinstance(expr, ExistsExpression):
            self.state.register_query(expr.query)
            return self.state.add_expr(
                {
                    "kind": "exists",
                    "query": expr.query.name,
                    "predicate": self.serialize_expr(expr.predicate),
                }
            )
        if isinstance(expr, GroupedAnyExpression):
            return self._serialize_grouped_any_expr(expr)
        if isinstance(expr, GroupedValueAggregateExpression):
            return self._serialize_grouped_value_expr(expr)
        spatial = self.spatial.serialize_spatial_expr(expr)
        if spatial is not None:
            return spatial
        if isinstance(expr, EntityExpression):
            raise PhysicalPlanUnsupported("entity handle expressions are not supported by Rust ECS")
        raise PhysicalPlanUnsupported(
            f"expression {type(expr).__name__} is not supported by Rust ECS execution"
        )

    def _serialize_loop_item(self, expr: LoopItem) -> int:
        slot = self.state.loop_item_slots.get(id(expr))
        if slot is None:
            raise SystemPlanError(f"ECS loop item {expr.name!r} is used outside for_each().")
        return self.state.add_expr({"kind": "for_each_item", "slot": slot})

    def _serialize_field_expr(self, expr: FieldExpression) -> int | None:
        self.state.world.validate_schema(expr.component_type)
        component = schema_name(expr.component_type)
        if isinstance(expr.source, QueryProxy):
            self.state.register_query(expr.source)
            return self.state.add_expr(
                {
                    "kind": "field",
                    "query": expr.source.name,
                    "component": component,
                    "field": expr.field_name,
                }
            )
        if isinstance(expr.source, ResourceProxy):
            return self.state.add_expr(
                {"kind": "resource_field", "resource": component, "field": expr.field_name}
            )
        return None

    def _serialize_grouped_any_expr(self, expr: GroupedAnyExpression) -> int:
        self.state.register_query(expr.query)
        return self.state.add_expr(
            {
                "kind": "aggregate",
                "aggregate": "any",
                "relation": self.serialize_expr(expr.expression),
                "group_query": expr.query.name,
            }
        )

    def _serialize_grouped_value_expr(self, expr: GroupedValueAggregateExpression) -> int:
        self.state.register_query(expr.query)
        node: BridgeNode = {
            "kind": "aggregate",
            "aggregate": expr.kind,
            "relation": self.serialize_expr(expr.expression),
            "group_query": expr.query.name,
        }
        if expr.value is not None:
            node["value"] = self.serialize_expr(expr.value)
        if expr.default is not None:
            node["default"] = self.serialize_literal(expr.default)
        return self.state.add_expr(node)

    def serialize_binary_expr(self, op: str, left: Expression, right: Expression) -> int:
        """Serialize a binary expression node."""

        return self.state.add_expr(
            {
                "kind": "binary",
                "op": op,
                "left": self.serialize_expr(left),
                "right": self.serialize_expr(right),
            }
        )

    def serialize_function_expr(self, expr: FunctionExpression) -> int:
        """Serialize supported built-in function expressions."""

        if expr.name in {"sqrt", "abs", "sin", "cos", "floor", "ceil"} and len(expr.args) == 1:
            return self.state.add_expr(
                {"kind": "unary", "op": expr.name, "input": self.serialize_expr(expr.args[0])}
            )
        if expr.name in {"min", "max"} and len(expr.args) == 2:
            return self.serialize_binary_expr(expr.name, expr.args[0], expr.args[1])
        if expr.name == "clamp" and len(expr.args) == 3:
            lower = self.serialize_binary_expr("max", expr.args[0], expr.args[1])
            return self.state.add_expr(
                {
                    "kind": "binary",
                    "op": "min",
                    "left": lower,
                    "right": self.serialize_expr(expr.args[2]),
                }
            )
        raise PhysicalPlanUnsupported(
            f"function {expr.name!r} is not supported by Rust ECS execution"
        )

    def serialize_literal(self, value: object) -> int:
        """Serialize a literal value and return its bridge expression index."""

        literal = bridge_literal_value(cast(EcsLiteralValue, value))
        return self._add_literal_expr(literal)

    def _add_literal_expr(self, value: BridgeLiteral) -> int:
        if isinstance(value, bool):
            return self.state.add_expr({"kind": "literal_bool", "value": value})
        if isinstance(value, int):
            if -(2**63) <= value <= 2**63 - 1:
                return self.state.add_expr({"kind": "literal_i64", "value": value})
            if 0 <= value <= 2**64 - 1:
                return self.state.add_expr({"kind": "literal_value", "value": value})
            raise PhysicalPlanUnsupported(
                f"integer literal {value!r} is outside the Rust ECS value range"
            )
        if isinstance(value, float):
            return self.state.add_expr({"kind": "literal_f64", "value": value})
        if isinstance(value, str):
            return self.state.add_expr({"kind": "literal_string", "value": value})
        return self.state.add_expr({"kind": "literal_value", "value": value})
