"""Explain-format helpers for ECS action plans."""

from __future__ import annotations

import builtins

from gummysnake.ecs.actions import (
    Action,
    DefaultAction,
    ExpressionIterableSource,
    ForEachAction,
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
)


def explain_action(action: Action) -> list[str]:
    """Return human-readable lines that describe an ECS action tree."""

    return _explain_action(action)


def _explain_action(action: Action, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    if isinstance(action, DefaultAction):
        if action.kind == "set" and action.target is not None:
            target = f"{action.target.component_type.__name__}.{action.target.field_name}"
            if action.value is None:
                return [f"{prefix}set {target}"]
            lines = [f"{prefix}set {target} <- {_explain_expr(action.value)}"]
            lines.extend(_explain_expr_details(action.value, indent + 1))
            return lines
        if action.kind in {"sequence", "parallel"}:
            label = "do_in_parallel" if action.kind == "parallel" else "do_in_order"
            lines = [f"{prefix}{label}"]
            for child in action.children:
                lines.extend(_explain_action(child, indent + 1))
            return lines
        if action.kind == "udf" and action.udf is not None:
            return [f"{prefix}udf {action.udf.function.__name__}"]
        if action.kind == "emit_event" and action.event_writer is not None:
            return [f"{prefix}emit_event {action.event_writer.event_type.__name__}"]
        if (
            action.kind in {"add_component", "remove_component"}
            and action.component_type is not None
        ):
            query = action.entity_query.name if action.entity_query is not None else "?"
            return [f"{prefix}{action.kind} {query}.{action.component_type.__name__}"]
        if action.kind in {"add_tag", "remove_tag"}:
            query = action.entity_query.name if action.entity_query is not None else "?"
            return [f"{prefix}{action.kind} {query}.{action.tag}"]
        if action.kind == "despawn":
            query = action.entity_query.name if action.entity_query is not None else "?"
            return [f"{prefix}despawn {query}"]
        if action.kind == "noop":
            return [f"{prefix}noop"]
        return [f"{prefix}{action.kind}"]
    if isinstance(action, WhenAction):
        lines = [f"{prefix}when_chain"]
        for index, (condition, branch) in enumerate(action.branches, start=1):
            lines.append(f"{prefix}  when[{index}] {_explain_expr(condition)}")
            lines.extend(_explain_expr_details(condition, indent + 2))
            lines.extend(_explain_action(branch, indent + 2))
        if action.otherwise_action is not None:
            lines.append(f"{prefix}  otherwise")
            lines.extend(_explain_action(action.otherwise_action, indent + 2))
        return lines
    if isinstance(action, ForEachAction):
        source = type(action.source).__name__.removesuffix("Source")
        lines = [f"{prefix}for_each {source} mode={action.mode}"]
        if isinstance(action.source, ExpressionIterableSource):
            lines.append(f"{prefix}  source {_explain_expr(action.source.expression)}")
            lines.extend(_explain_expr_details(action.source.expression, indent + 1))
        lines.extend(_explain_action(action.body, indent + 1))
        return lines
    return [f"{prefix}{type(action).__name__}"]


def _explain_expr(expr: Expression) -> str:
    if isinstance(expr, LiteralExpression):
        return repr(expr.value)
    if isinstance(expr, FieldExpression):
        return f"{_source_name(expr.source)}.{expr.component_type.__name__}.{expr.field_name}"
    if isinstance(expr, EntityExpression):
        return f"{expr.query.name}.entity"
    if isinstance(expr, UnaryExpression):
        op = "~" if expr.op == "not" else expr.op
        return f"({op}{_explain_expr(expr.operand)})"
    if isinstance(expr, BinaryExpression):
        return f"({_explain_expr(expr.left)} {expr.op} {_explain_expr(expr.right)})"
    if isinstance(expr, AttributeExpression):
        return f"{_explain_expr(expr.base)}.{expr.attribute}"
    if isinstance(expr, FunctionExpression):
        args = ", ".join(_explain_expr(arg) for arg in expr.args)
        return f"{expr.name}({args})"
    if isinstance(expr, DeltatimeExpression):
        return "dt()"
    if isinstance(expr, KeyDownExpression):
        return f"key_is_down({expr.key!r})"
    if isinstance(expr, GroupedAnyExpression):
        return f"group_by({expr.query.name}).any({_explain_expr(expr.expression)})"
    if isinstance(expr, GroupedValueAggregateExpression):
        value = "" if expr.value is None else f", value={_explain_expr(expr.value)}"
        return f"group_by({expr.query.name}).{expr.kind}({_explain_expr(expr.expression)}{value})"
    if isinstance(expr, ExistsExpression):
        return f"exists({expr.query.name}).where({_explain_expr(expr.predicate)})"
    spatial = _explain_spatial_expr(expr)
    if spatial is not None:
        return spatial
    return type(expr).__name__


def _source_name(source: QueryProxy | ResourceProxy) -> str:
    if isinstance(source, QueryProxy):
        return source.name
    mode = "ResMut" if source.mutable else "Res"
    return f"{mode}({source.name})"


def _explain_expr_details(expr: Expression, indent: int) -> list[str]:
    prefix = "  " * indent
    relations = _collect_spatial_relations(expr)
    return [f"{prefix}{_explain_spatial_relation(relation)}" for relation in relations]


def _explain_spatial_expr(expr: Expression) -> str | None:
    from gummysnake.ecs.spatial import SpatialAggregateExpression, SpatialMetadataExpression

    if isinstance(expr, SpatialAggregateExpression):
        value = "" if expr.value is None else f", value={_explain_expr(expr.value)}"
        return f"spatial.{expr.kind}({expr.relation.name or expr.relation.item.name}{value})"
    if isinstance(expr, SpatialMetadataExpression):
        relation_name = expr.relation.name or expr.relation.item.name
        if expr.kind == "delta" and expr.axis is not None:
            axis = "xyz"[expr.axis]
            return f"spatial.{relation_name}.delta.{axis}"
        return f"spatial.{relation_name}.{expr.kind}"
    return None


def _collect_spatial_relations(expr: Expression) -> tuple[object, ...]:
    from gummysnake.ecs.spatial import SpatialAggregateExpression, SpatialMetadataExpression

    found: list[object] = []
    seen: builtins.set[int] = builtins.set()

    def add_relation(relation: object) -> None:
        key = id(relation)
        if key not in seen:
            seen.add(key)
            found.append(relation)

    def walk(node: Expression) -> None:
        if isinstance(node, SpatialAggregateExpression):
            add_relation(node.relation)
            if node.value is not None:
                walk(node.value)
            return
        if isinstance(node, SpatialMetadataExpression):
            add_relation(node.relation)
            return
        if isinstance(node, BinaryExpression):
            walk(node.left)
            walk(node.right)
            return
        if isinstance(node, UnaryExpression):
            walk(node.operand)
            return
        if isinstance(node, FunctionExpression):
            for arg in node.args:
                walk(arg)
            return
        if isinstance(node, AttributeExpression):
            walk(node.base)
            return
        if isinstance(node, GroupedAnyExpression | GroupedValueAggregateExpression):
            walk(node.expression)
            if node.value is not None:
                walk(node.value)
            return
        if isinstance(node, ExistsExpression):
            walk(node.predicate)

    walk(expr)
    return tuple(found)


def _explain_spatial_relation(relation: object) -> str:
    algorithm = getattr(relation, "algorithm", None)
    kind = getattr(algorithm, "kind", type(algorithm).__name__ if algorithm is not None else "none")
    name = getattr(relation, "name", None) or getattr(
        getattr(relation, "item", None), "name", "relation"
    )
    dimensions = getattr(relation, "dimensions", "?")
    origin = getattr(getattr(relation, "origin", None), "name", "?")
    target = getattr(getattr(relation, "item", None), "name", "?")
    predicates: list[str] = []
    if getattr(relation, "radius", None) is not None:
        predicates.append("radius")
    if getattr(relation, "origin_bounds", None) is not None:
        predicates.append("aabb")
    if getattr(relation, "exact_filter", None) is not None:
        predicates.append("exact_filter")
    pair_policy = getattr(relation, "pair_policy", "all")
    predicate_text = ",".join(predicates) if predicates else "all"
    return (
        "spatial_relation "
        f"name={name} algorithm={kind} dimensions={dimensions} "
        f"origin={origin} target={target} predicates={predicate_text} "
        f"pair_policy={pair_policy}"
    )


