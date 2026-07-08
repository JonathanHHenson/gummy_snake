"""Action serialization for ECS physical payloads."""

from __future__ import annotations

from gummysnake.ecs.actions import (
    Action,
    DefaultAction,
    EventIterableSource,
    ExpressionIterableSource,
    ForEachAction,
    IterableSource,
    LoopItem,
    UdfIterableSource,
    WhenAction,
)
from gummysnake.ecs.expressions import ResourceProxy, expression_queries
from gummysnake.ecs.physical_payload.expressions import ExpressionSerializer
from gummysnake.ecs.physical_payload.helpers import bridge_literal_value, schema_name
from gummysnake.ecs.physical_payload.types import BridgeNode, PayloadState, PhysicalPlanUnsupported
from gummysnake.exceptions import SystemPlanError


class ActionSerializer:
    """Serialize ECS action trees into Rust bridge action nodes."""

    def __init__(self, state: PayloadState, expressions: ExpressionSerializer) -> None:
        self.state = state
        self.expressions = expressions

    def serialize_action(self, action: Action) -> int:
        """Serialize a supported ECS action and return its bridge action index."""

        if isinstance(action, DefaultAction):
            return self.serialize_default_action(action)
        if isinstance(action, WhenAction):
            return self.serialize_when_action(action)
        if isinstance(action, ForEachAction):
            return self.serialize_for_each_action(action)
        raise PhysicalPlanUnsupported(
            f"action {type(action).__name__} is not supported by Rust ECS execution"
        )

    def serialize_default_action(self, action: DefaultAction) -> int:
        """Serialize a leaf, sequence, parallel, event, or structural action."""

        if action.kind == "noop":
            return self.state.add_action({"kind": "noop"})
        if action.kind == "set":
            return self._serialize_set_action(action)
        if action.kind in {"sequence", "parallel"}:
            return self.state.add_action(
                {
                    "kind": action.kind,
                    "children": [self.serialize_action(child) for child in action.children],
                }
            )
        if action.kind == "udf":
            raise PhysicalPlanUnsupported("Python UDF actions require explicit Python execution")
        if action.kind == "emit_event":
            return self._serialize_emit_event_action(action)
        if action.kind == "canvas":
            return self._serialize_canvas_action(action)
        if action.kind in {"add_component", "remove_component", "add_tag", "remove_tag", "despawn"}:
            return self.serialize_structural_action(action)
        raise PhysicalPlanUnsupported(
            f"action kind {action.kind!r} is not supported by Rust ECS execution"
        )

    def _serialize_set_action(self, action: DefaultAction) -> int:
        if action.target is None or action.value is None:
            raise SystemPlanError("Malformed ECS set action.")
        if isinstance(action.target.source, ResourceProxy) and not action.target.source.mutable:
            raise PhysicalPlanUnsupported("read-only resource writes are not allowed")
        return self.state.add_action(
            {
                "kind": "set_field",
                "target": self.expressions.serialize_expr(action.target),
                "value": self.expressions.serialize_expr(action.value),
            }
        )

    def _serialize_canvas_action(self, action: DefaultAction) -> int:
        if action.canvas_command is None:
            raise SystemPlanError("Malformed ECS canvas action.")
        return self.state.add_action(
            {
                "kind": "canvas_command",
                "command": action.canvas_command,
                "args": [self.expressions.serialize_expr(arg) for arg in action.canvas_args],
            }
        )

    def _serialize_emit_event_action(self, action: DefaultAction) -> int:
        if action.event_writer is None or action.event_value is None:
            raise SystemPlanError("Malformed ECS emit_event action.")
        event_type = action.event_writer.event_type
        self.state.world._register_event_type(event_type)
        if type(action.event_value) is not event_type:
            actual_type = type(action.event_value).__name__
            raise SystemPlanError(f"Expected ECS event {event_type.__name__}, got {actual_type}.")
        return self.state.add_action(
            {
                "kind": "emit_event",
                "event_type": schema_name(event_type),
                "value": self.expressions.serialize_literal(action.event_value),
            }
        )

    def serialize_structural_action(self, action: DefaultAction) -> int:
        """Serialize entity, component, and tag structural commands."""

        if action.entity_query is None:
            raise SystemPlanError(f"Malformed ECS structural action {action.kind!r}.")
        self.state.register_query(action.entity_query)
        node: BridgeNode = {"kind": action.kind, "query": action.entity_query.name}
        if action.kind in {"add_component", "remove_component"}:
            if action.component_type is None:
                raise SystemPlanError(f"Malformed ECS {action.kind} action.")
            self.state.world.validate_schema(action.component_type)
            node["component"] = schema_name(action.component_type)
            if action.kind == "add_component" and action.component_value is not None:
                node["value"] = self.expressions.serialize_literal(action.component_value)
        elif action.kind in {"add_tag", "remove_tag"}:
            if action.tag is None:
                raise SystemPlanError(f"Malformed ECS {action.kind} action.")
            tag = str(action.tag)
            if not tag:
                raise SystemPlanError("ECS tag values cannot be empty.")
            node["tag"] = tag
        return self.state.add_action(node)

    def serialize_when_action(self, action: WhenAction) -> int:
        """Serialize conditional branches into nested Rust bridge ``when`` actions."""

        if not action.branches:
            if action.otherwise_action is None:
                return self.state.add_action({"kind": "noop"})
            return self.serialize_action(action.otherwise_action)
        otherwise = (
            self.serialize_action(action.otherwise_action)
            if action.otherwise_action is not None
            else None
        )
        next_action = otherwise
        for condition, branch_action in reversed(action.branches):
            next_action = self.state.add_action(
                {
                    "kind": "when",
                    "condition": self.expressions.serialize_expr(condition),
                    "then_action": self.serialize_action(branch_action),
                    "otherwise_action": next_action,
                }
            )
        assert next_action is not None
        return next_action

    def serialize_for_each_action(self, action: ForEachAction) -> int:
        """Serialize a for-each action and its iterable source."""

        item = getattr(action.source, "item", None)
        if not isinstance(item, LoopItem):
            raise SystemPlanError("Malformed ECS for_each action.")
        item_slot = self.state.loop_item_slots.setdefault(id(item), self.state.next_loop_item_slot)
        if item_slot == self.state.next_loop_item_slot:
            self.state.next_loop_item_slot += 1

        source = self.serialize_for_each_source(action.source)
        body = self.serialize_action(action.body)
        for_each = self.state.add_action(
            {"kind": "for_each", "source": source, "item_slot": item_slot, "action": body}
        )

        if isinstance(action.source, ExpressionIterableSource) and expression_queries(
            action.source.expression
        ):
            condition = self.serialize_query_binding_condition(source)
            return self.state.add_action(
                {
                    "kind": "when",
                    "condition": condition,
                    "then_action": for_each,
                    "otherwise_action": None,
                }
            )
        return for_each

    def serialize_for_each_source(self, source: IterableSource) -> int:
        """Serialize the iterable source for a for-each action."""

        if isinstance(source, ExpressionIterableSource):
            return self.expressions.serialize_expr(source.expression)
        if isinstance(source, EventIterableSource):
            self.state.world._register_event_type(source.reader.event_type)
            return self.state.add_expr(
                {"kind": "event_stream", "event_type": schema_name(source.reader.event_type)}
            )
        if isinstance(source, UdfIterableSource):
            self.state.mark_dynamic()
            values = list(source.evaluate(self.state.world))
            self.state.world._diagnostics["ecs_udf_calls"] += 1
            return self.state.add_expr(
                {
                    "kind": "literal_value",
                    "value": [bridge_literal_value(value) for value in values],
                }
            )
        raise PhysicalPlanUnsupported(
            f"for_each source {type(source).__name__} is not supported by Rust ECS execution"
        )

    def serialize_query_binding_condition(self, source: int) -> int:
        """Create the guard expression used for query-bound iterable sources."""

        literal_true = self.state.add_expr({"kind": "literal_bool", "value": True})
        return self.state.add_expr(
            {"kind": "binary", "op": "or", "left": literal_true, "right": source}
        )
