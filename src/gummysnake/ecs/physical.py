"""Serialization of Python ECS action trees into Rust physical-plan payloads."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any, cast

from gummysnake.ecs.actions import (
    DefaultAction,
    EventIterableSource,
    ExpressionIterableSource,
    ForEachAction,
    LoopItem,
    UdfCallExpression,
    UdfIterableSource,
    WhenAction,
)
from gummysnake.ecs.expressions import (
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
    expression_queries,
)
from gummysnake.ecs.specs import ChangeTerm, QuerySpec, TagTerm, WithoutTerm
from gummysnake.exceptions import SystemPlanError

BRIDGE_PLAN_VERSION = 2


@dataclass(frozen=True)
class PhysicalPlanUnsupported(Exception):
    """Raised internally when a non-UDF node cannot be serialized for Rust execution."""

    reason: str

    def __str__(self) -> str:
        return self.reason


class _PhysicalPayloadBuilder:
    def __init__(self, world: Any, built: Any) -> None:
        self.world = world
        self.built = built
        self.expressions: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self._expr_indices: dict[int, int] = {}
        self._queries: dict[str, QueryProxy] = {}
        self._loop_item_slots: dict[int, int] = {}
        self._next_loop_item_slot = 0
        self.dynamic = False
        for query in self.built.queries:
            self._register_query(query)

    def build(self) -> dict[str, Any]:
        root_action = self._serialize_action(self.built.plan.action)
        queries = [self._query_payload(query) for query in self._queries.values()]
        return {
            "version": BRIDGE_PLAN_VERSION,
            "schema_fingerprint": self.world._rust.schema_fingerprint(),
            "queries": queries,
            "expressions": self.expressions,
            "actions": self.actions,
            "root_action": root_action,
            "dynamic": self.dynamic,
        }

    def _register_query(self, query: QueryProxy) -> None:
        existing = self._queries.get(query.name)
        if existing is not None:
            if existing.spec != query.spec:
                raise SystemPlanError(
                    f"ECS query name {query.name!r} is used for incompatible specifications."
                )
            return
        self._queries[query.name] = query

    def _query_payload(self, query: QueryProxy) -> dict[str, Any]:
        spec = query.spec
        if not isinstance(spec, QuerySpec):
            raise PhysicalPlanUnsupported(f"query {query.name!r} has an unsupported specification")
        terms: list[tuple[str, str]] = []
        seen_terms: set[tuple[str, str]] = set()
        change_terms: list[ChangeTerm] = []

        def add_term(kind: str, name: str) -> None:
            term = (kind, name)
            if term not in seen_terms:
                seen_terms.add(term)
                terms.append(term)

        for term in spec.terms:
            if isinstance(term, TagTerm):
                tag = str(term.value)
                if not tag:
                    raise SystemPlanError("ECS tag values cannot be empty.")
                add_term("with_tag", tag)
            elif isinstance(term, WithoutTerm):
                value = term.value
                if isinstance(value, TagTerm):
                    tag = str(value.value)
                    if not tag:
                        raise SystemPlanError("ECS tag values cannot be empty.")
                    add_term("without_tag", tag)
                elif isinstance(value, type):
                    self.world.validate_schema(value)
                    add_term("without_component", _schema_name(value))
                else:
                    raise PhysicalPlanUnsupported(f"unsupported ecs.Without query term {value!r}")
            elif isinstance(term, ChangeTerm):
                self.world.validate_schema(term.component_type)
                change_terms.append(term)
                if term.kind != "removed":
                    add_term("with_component", _schema_name(term.component_type))
            elif isinstance(term, type):
                self.world.validate_schema(term)
                add_term("with_component", _schema_name(term))
            else:
                raise PhysicalPlanUnsupported(f"unsupported query term {term!r}")

        payload: dict[str, Any] = {"name": query.name, "terms": terms}
        if change_terms:
            self._mark_dynamic()
            matches = self.world.match_query(spec)
            payload["allowed_entities"] = [
                (int(entity.entity.index), int(entity.entity.generation)) for entity in matches
            ]
        return payload

    def _add_expr(self, node: dict[str, Any]) -> int:
        self.expressions.append(node)
        return len(self.expressions) - 1

    def _add_action(self, node: dict[str, Any]) -> int:
        self.actions.append(node)
        return len(self.actions) - 1

    def _mark_dynamic(self) -> None:
        self.dynamic = True

    def _serialize_expr(self, expr: Expression) -> int:
        cached = self._expr_indices.get(id(expr))
        if cached is not None:
            return cached
        index = self._serialize_expr_uncached(expr)
        self._expr_indices[id(expr)] = index
        return index

    def _serialize_expr_uncached(self, expr: Expression) -> int:
        if isinstance(expr, LiteralExpression):
            return self._serialize_literal(expr.value)
        if isinstance(expr, LoopItem):
            slot = self._loop_item_slots.get(id(expr))
            if slot is None:
                raise SystemPlanError(f"ECS loop item {expr.name!r} is used outside for_each().")
            return self._add_expr({"kind": "for_each_item", "slot": slot})
        if isinstance(expr, FieldExpression):
            self.world.validate_schema(expr.component_type)
            component = _schema_name(expr.component_type)
            if isinstance(expr.source, QueryProxy):
                self._register_query(expr.source)
                return self._add_expr(
                    {
                        "kind": "field",
                        "query": expr.source.name,
                        "component": component,
                        "field": expr.field_name,
                    }
                )
            if isinstance(expr.source, ResourceProxy):
                return self._add_expr(
                    {
                        "kind": "resource_field",
                        "resource": component,
                        "field": expr.field_name,
                    }
                )
        if isinstance(expr, AttributeExpression):
            return self._add_expr(
                {
                    "kind": "attribute",
                    "input": self._serialize_expr(expr.base),
                    "attribute": expr.attribute,
                }
            )
        if isinstance(expr, UnaryExpression):
            return self._add_expr(
                {
                    "kind": "unary",
                    "op": expr.op,
                    "input": self._serialize_expr(expr.operand),
                }
            )
        if isinstance(expr, BinaryExpression):
            return self._serialize_binary_expr(expr.op, expr.left, expr.right)
        if isinstance(expr, FunctionExpression):
            return self._serialize_function_expr(expr)
        if isinstance(expr, UdfCallExpression):
            raise PhysicalPlanUnsupported(
                f"Rust-backed UDF {expr.definition.function.__name__!r} has no registered "
                "Rust executor"
            )
        if isinstance(expr, DeltatimeExpression):
            return self._add_expr({"kind": "input_state", "name": "dt"})
        if isinstance(expr, KeyDownExpression):
            return self._add_expr(
                {"kind": "input_state", "name": "key_down", "code": _key_code(expr.key)}
            )
        if isinstance(expr, ExistsExpression):
            self._register_query(expr.query)
            return self._add_expr(
                {
                    "kind": "exists",
                    "query": expr.query.name,
                    "predicate": self._serialize_expr(expr.predicate),
                }
            )
        if isinstance(expr, GroupedAnyExpression):
            self._register_query(expr.query)
            return self._add_expr(
                {
                    "kind": "aggregate",
                    "aggregate": "any",
                    "relation": self._serialize_expr(expr.expression),
                    "group_query": expr.query.name,
                }
            )
        if isinstance(expr, GroupedValueAggregateExpression):
            self._register_query(expr.query)
            node: dict[str, Any] = {
                "kind": "aggregate",
                "aggregate": expr.kind,
                "relation": self._serialize_expr(expr.expression),
                "group_query": expr.query.name,
            }
            if expr.value is not None:
                node["value"] = self._serialize_expr(expr.value)
            if expr.default is not None:
                node["default"] = self._serialize_literal(expr.default)
            return self._add_expr(node)
        spatial = self._serialize_spatial_expr(expr)
        if spatial is not None:
            return spatial
        if isinstance(expr, EntityExpression):
            raise PhysicalPlanUnsupported("entity handle expressions are not supported by Rust ECS")
        raise PhysicalPlanUnsupported(
            f"expression {type(expr).__name__} is not supported by Rust ECS execution"
        )

    def _serialize_binary_expr(self, op: str, left: Expression, right: Expression) -> int:
        return self._add_expr(
            {
                "kind": "binary",
                "op": op,
                "left": self._serialize_expr(left),
                "right": self._serialize_expr(right),
            }
        )

    def _serialize_function_expr(self, expr: FunctionExpression) -> int:
        if expr.name in {"sqrt", "abs", "sin", "cos", "floor", "ceil"} and len(expr.args) == 1:
            return self._add_expr(
                {
                    "kind": "unary",
                    "op": expr.name,
                    "input": self._serialize_expr(expr.args[0]),
                }
            )
        if expr.name in {"min", "max"} and len(expr.args) == 2:
            return self._serialize_binary_expr(expr.name, expr.args[0], expr.args[1])
        if expr.name == "clamp" and len(expr.args) == 3:
            lower = self._serialize_binary_expr("max", expr.args[0], expr.args[1])
            return self._add_expr(
                {
                    "kind": "binary",
                    "op": "min",
                    "left": lower,
                    "right": self._serialize_expr(expr.args[2]),
                }
            )
        raise PhysicalPlanUnsupported(
            f"function {expr.name!r} is not supported by Rust ECS execution"
        )

    def _serialize_literal(self, value: object) -> int:
        value = _bridge_literal_value(value)
        if isinstance(value, bool):
            return self._add_expr({"kind": "literal_bool", "value": value})
        if isinstance(value, int) and not isinstance(value, bool):
            if -(2**63) <= value <= 2**63 - 1:
                return self._add_expr({"kind": "literal_i64", "value": value})
            if 0 <= value <= 2**64 - 1:
                return self._add_expr({"kind": "literal_value", "value": value})
            raise PhysicalPlanUnsupported(
                f"integer literal {value!r} is outside the Rust ECS value range"
            )
        if isinstance(value, float):
            return self._add_expr({"kind": "literal_f64", "value": value})
        if isinstance(value, str):
            return self._add_expr({"kind": "literal_string", "value": value})
        return self._add_expr({"kind": "literal_value", "value": value})

    def _serialize_spatial_expr(self, expr: Expression) -> int | None:
        from gummysnake.ecs.spatial import SpatialAggregateExpression, SpatialMetadataExpression

        if isinstance(expr, SpatialMetadataExpression):
            node: dict[str, Any] = {
                "kind": "spatial_metadata",
                "relation": self._serialize_spatial_relation(expr.relation),
                "metadata": expr.kind,
            }
            if expr.axis is not None:
                node["axis"] = int(expr.axis)
            return self._add_expr(node)
        if isinstance(expr, SpatialAggregateExpression):
            node = {
                "kind": "spatial_aggregate",
                "aggregate": expr.kind,
                "relation": self._serialize_spatial_relation(expr.relation),
            }
            if expr.value is not None:
                node["value"] = self._serialize_expr(expr.value)
            if expr.default is not None:
                node["default"] = self._serialize_literal(expr.default)
            return self._add_expr(node)
        return None

    def _serialize_spatial_relation(self, relation: Any) -> dict[str, Any]:
        self._register_query(relation.origin)
        self._register_query(relation.item)
        relation_id = relation.name or f"spatial_relation:{id(relation)}"
        origin_position = self._serialize_spatial_point(relation.origin_position)
        target_position = self._serialize_spatial_point(relation.target_position)
        target_bounds = (
            self._serialize_spatial_bounds(relation.target_bounds)
            if relation.target_bounds is not None
            else None
        )
        algorithm = self._serialize_spatial_algorithm(relation)
        node: dict[str, Any] = {
            "id": relation_id,
            "index_id": self._spatial_relation_index_id(
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
            node["radius"] = self._serialize_expr(relation.radius)
        if relation.origin_bounds is not None:
            node["origin_bounds"] = self._serialize_spatial_bounds(relation.origin_bounds)
        if target_bounds is not None:
            node["target_bounds"] = target_bounds
        if relation.exact_filter is not None:
            node["exact_filter"] = self._serialize_expr(relation.exact_filter)
        return node

    def _spatial_relation_index_id(
        self,
        relation: Any,
        target_position: list[int],
        target_bounds: dict[str, list[int]] | None,
        algorithm: dict[str, Any],
    ) -> str:
        return (
            "spatial_index:"
            f"item={relation.item.name};"
            f"target_position={target_position!r};"
            f"target_bounds={target_bounds!r};"
            f"algorithm={algorithm!r}"
        )

    def _serialize_spatial_point(self, point: Any) -> list[int]:
        return [self._serialize_expr(expr) for expr in point.expressions]

    def _serialize_spatial_bounds(self, bounds: Any) -> dict[str, list[int]]:
        return {
            "minimum": self._serialize_spatial_point(bounds.min_point),
            "maximum": self._serialize_spatial_point(bounds.max_point),
        }

    def _serialize_spatial_algorithm(self, relation: Any) -> dict[str, Any]:
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
        node: dict[str, Any] = {"kind": algorithm.kind, "dimensions": int(dimensions)}
        if isinstance(algorithm, HashGrid):
            node["cell_size"] = float(algorithm.cell_size)
        elif isinstance(algorithm, Quadtree | Octree):
            node["bounds"] = _spatial_bounds_values(algorithm.bounds)
            node["capacity"] = int(algorithm.capacity)
        elif isinstance(algorithm, HilbertCurve):
            if not isinstance(algorithm.bounds, Bounds2D | Bounds3D):
                raise SystemPlanError("HilbertCurve bounds must be Bounds2D or Bounds3D.")
            node["bounds"] = _spatial_bounds_values(algorithm.bounds)
            node["bits"] = int(algorithm.bits)
        else:
            raise PhysicalPlanUnsupported(
                f"spatial algorithm {type(algorithm).__name__} is not supported by "
                "Rust ECS execution"
            )
        return node

    def _serialize_action(self, action: Any) -> int:
        if isinstance(action, DefaultAction):
            return self._serialize_default_action(action)
        if isinstance(action, WhenAction):
            return self._serialize_when_action(action)
        if isinstance(action, ForEachAction):
            return self._serialize_for_each_action(action)
        raise PhysicalPlanUnsupported(
            f"action {type(action).__name__} is not supported by Rust ECS execution"
        )

    def _serialize_default_action(self, action: DefaultAction) -> int:
        if action.kind == "noop":
            return self._add_action({"kind": "noop"})
        if action.kind == "set":
            if action.target is None or action.value is None:
                raise SystemPlanError("Malformed ECS set action.")
            if isinstance(action.target.source, ResourceProxy) and not action.target.source.mutable:
                raise PhysicalPlanUnsupported("read-only resource writes are not allowed")
            return self._add_action(
                {
                    "kind": "set_field",
                    "target": self._serialize_expr(action.target),
                    "value": self._serialize_expr(action.value),
                }
            )
        if action.kind == "sequence":
            return self._add_action(
                {
                    "kind": "sequence",
                    "children": [self._serialize_action(child) for child in action.children],
                }
            )
        if action.kind == "parallel":
            return self._add_action(
                {
                    "kind": "parallel",
                    "children": [self._serialize_action(child) for child in action.children],
                }
            )
        if action.kind == "udf":
            raise PhysicalPlanUnsupported("Python UDF actions require explicit Python execution")
        if action.kind == "emit_event":
            if action.event_writer is None or action.event_value is None:
                raise SystemPlanError("Malformed ECS emit_event action.")
            event_type = action.event_writer.event_type
            self.world._register_event_type(event_type)
            if type(action.event_value) is not event_type:
                raise SystemPlanError(
                    f"Expected ECS event {event_type.__name__}, "
                    f"got {type(action.event_value).__name__}."
                )
            return self._add_action(
                {
                    "kind": "emit_event",
                    "event_type": _event_type_name(event_type),
                    "value": self._serialize_literal(action.event_value),
                }
            )
        if action.kind in {"add_component", "remove_component", "add_tag", "remove_tag", "despawn"}:
            return self._serialize_structural_action(action)
        raise PhysicalPlanUnsupported(
            f"action kind {action.kind!r} is not supported by Rust ECS execution"
        )

    def _serialize_structural_action(self, action: DefaultAction) -> int:
        if action.entity_query is None:
            raise SystemPlanError(f"Malformed ECS structural action {action.kind!r}.")
        self._register_query(action.entity_query)
        node: dict[str, Any] = {"kind": action.kind, "query": action.entity_query.name}
        if action.kind in {"add_component", "remove_component"}:
            if action.component_type is None:
                raise SystemPlanError(f"Malformed ECS {action.kind} action.")
            self.world.validate_schema(action.component_type)
            node["component"] = _schema_name(action.component_type)
            if action.kind == "add_component" and action.component_value is not None:
                node["value"] = self._serialize_literal(action.component_value)
        elif action.kind in {"add_tag", "remove_tag"}:
            if action.tag is None:
                raise SystemPlanError(f"Malformed ECS {action.kind} action.")
            tag = str(action.tag)
            if not tag:
                raise SystemPlanError("ECS tag values cannot be empty.")
            node["tag"] = tag
        return self._add_action(node)

    def _serialize_when_action(self, action: WhenAction) -> int:
        if not action.branches:
            if action.otherwise_action is None:
                return self._add_action({"kind": "noop"})
            return self._serialize_action(action.otherwise_action)
        otherwise = (
            self._serialize_action(action.otherwise_action)
            if action.otherwise_action is not None
            else None
        )
        next_action = otherwise
        for condition, branch_action in reversed(action.branches):
            next_action = self._add_action(
                {
                    "kind": "when",
                    "condition": self._serialize_expr(condition),
                    "then_action": self._serialize_action(branch_action),
                    "otherwise_action": next_action,
                }
            )
        assert next_action is not None
        return next_action

    def _serialize_for_each_action(self, action: ForEachAction) -> int:
        item = getattr(action.source, "item", None)
        if not isinstance(item, LoopItem):
            raise SystemPlanError("Malformed ECS for_each action.")
        item_slot = self._loop_item_slots.setdefault(id(item), self._next_loop_item_slot)
        if item_slot == self._next_loop_item_slot:
            self._next_loop_item_slot += 1

        source = self._serialize_for_each_source(action.source)
        body = self._serialize_action(action.body)
        for_each = self._add_action(
            {"kind": "for_each", "source": source, "item_slot": item_slot, "action": body}
        )

        if isinstance(action.source, ExpressionIterableSource) and expression_queries(
            action.source.expression
        ):
            condition = self._serialize_query_binding_condition(source)
            return self._add_action(
                {
                    "kind": "when",
                    "condition": condition,
                    "then_action": for_each,
                    "otherwise_action": None,
                }
            )
        return for_each

    def _serialize_for_each_source(self, source: Any) -> int:
        if isinstance(source, ExpressionIterableSource):
            return self._serialize_expr(source.expression)
        if isinstance(source, EventIterableSource):
            self.world._register_event_type(source.reader.event_type)
            return self._add_expr(
                {
                    "kind": "event_stream",
                    "event_type": _event_type_name(source.reader.event_type),
                }
            )
        if isinstance(source, UdfIterableSource):
            self._mark_dynamic()
            values = list(source.evaluate(self.world))
            self.world._diagnostics["ecs_udf_calls"] += 1
            return self._add_expr(
                {
                    "kind": "literal_value",
                    "value": [_bridge_literal_value(value) for value in values],
                }
            )
        raise PhysicalPlanUnsupported(
            f"for_each source {type(source).__name__} is not supported by Rust ECS execution"
        )

    def _serialize_query_binding_condition(self, source: int) -> int:
        literal_true = self._add_expr({"kind": "literal_bool", "value": True})
        return self._add_expr({"kind": "binary", "op": "or", "left": literal_true, "right": source})


def build_physical_payload(world: Any, built: Any) -> dict[str, Any]:
    """Build a Rust bridge payload or raise ``PhysicalPlanUnsupported``."""

    return _PhysicalPayloadBuilder(world, built).build()


def _schema_name(component_type: type[Any]) -> str:
    return f"{component_type.__module__}.{component_type.__qualname__}"


def _event_type_name(event_type: type[Any]) -> str:
    return _schema_name(event_type)


def _key_code(key: int | str) -> int:
    if isinstance(key, int):
        return key
    if len(key) == 1:
        return ord(key)
    raise PhysicalPlanUnsupported(
        f"key_is_down() Rust input nodes require integer or one-character keys, got {key!r}"
    )


def _bridge_literal_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        dataclass_value = cast(Any, value)
        return {
            field.name: _bridge_literal_value(getattr(dataclass_value, field.name))
            for field in fields(dataclass_value)
        }
    if isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [_bridge_literal_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_bridge_literal_value(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _bridge_literal_value(item) for key, item in value.items()}
    raise PhysicalPlanUnsupported(f"literal value {value!r} is not supported by Rust ECS execution")


def _spatial_bounds_values(bounds: Any) -> list[float]:
    if hasattr(bounds, "min_z"):
        return [
            float(bounds.min_x),
            float(bounds.min_y),
            float(bounds.min_z),
            float(bounds.max_x),
            float(bounds.max_y),
            float(bounds.max_z),
        ]
    return [float(bounds.min_x), float(bounds.min_y), float(bounds.max_x), float(bounds.max_y)]


__all__ = ["BRIDGE_PLAN_VERSION", "PhysicalPlanUnsupported", "build_physical_payload"]
