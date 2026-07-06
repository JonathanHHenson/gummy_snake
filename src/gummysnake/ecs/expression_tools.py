"""Helper functions for lazy ECS expressions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import is_dataclass
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.value_types import EcsLiteralValue

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.expressions import ExistsBuilder, Expression, QueryProxy
    from gummysnake.ecs.specs import Query
    from gummysnake.ecs.world import EcsWorld


type ExpressionInput = Expression | EcsLiteralValue


def _cached_expression_eval(
    expr: Expression,
    ctx: dict[object, Any],
    world: EcsWorld,
    compute: Callable[[], Any],
) -> Any:
    cache = getattr(world, "_expression_eval_cache", None)
    if cache is None:
        return compute()
    key = (id(expr), _expression_context_key(ctx))
    if key in cache:
        world._diagnostics["ecs_expression_cache_hits"] += 1
        return cache[key]
    world._diagnostics["ecs_expression_cache_misses"] += 1
    result = compute()
    cache[key] = result
    return result


def _expression_context_key(ctx: dict[object, Any]) -> tuple[object, ...]:
    parts: list[tuple[object, ...]] = []
    for key, value in ctx.items():
        if hasattr(value, "entity"):
            entity = value.entity
            parts.append(
                ("entity", id(key), int(entity.world_id), int(entity.index), int(entity.generation))
            )
        else:
            parts.append(("value", id(key), _expression_value_key(value)))
    return tuple(sorted(parts))


def _expression_value_key(value: object) -> object:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if is_dataclass(value):
        return repr(value)
    return id(value)


def ensure_expr(value: ExpressionInput) -> Expression:
    from gummysnake.ecs.expressions import Expression, LiteralExpression

    if isinstance(value, Expression):
        return value
    return LiteralExpression(value)


def all_of(*conditions: ExpressionInput) -> Expression:
    """Combine conditions with lazy ECS ``and``.

    Args:
        conditions: Values or expressions that should all be true.

    Returns:
        A lazy ECS expression representing every condition joined with ``&``.
    """
    from gummysnake.ecs.expressions import LiteralExpression

    if not conditions:
        return LiteralExpression(True)
    expr = ensure_expr(conditions[0])
    for condition in conditions[1:]:
        expr = expr & ensure_expr(condition)
    return expr


def any_of(*conditions: ExpressionInput) -> Expression:
    """Combine conditions with lazy ECS ``or``.

    Args:
        conditions: Values or expressions where at least one should be true.

    Returns:
        A lazy ECS expression representing the conditions joined with ``|``.
    """
    from gummysnake.ecs.expressions import LiteralExpression

    if not conditions:
        return LiteralExpression(False)
    expr = ensure_expr(conditions[0])
    for condition in conditions[1:]:
        expr = expr | ensure_expr(condition)
    return expr


def literal(value: EcsLiteralValue) -> Expression:
    """Wrap a Python value as a lazy ECS literal expression.

    Args:
        value: Python value to embed in a logical ECS plan.

    Returns:
        A literal expression containing ``value``.
    """
    from gummysnake.ecs.expressions import LiteralExpression

    return LiteralExpression(value)


def dt() -> Expression:
    """Return a lazy expression for the current sketch delta time.

    Returns:
        An expression that evaluates to seconds since the previous frame.
    """
    from gummysnake.ecs.expressions import DeltatimeExpression

    return DeltatimeExpression()


def key_is_down(key: int | str) -> Expression:
    """Return a lazy expression that checks whether a key is held.

    Args:
        key: Key name or key code to query at ECS execution time.

    Returns:
        A boolean expression for the current input state.
    """
    from gummysnake.ecs.expressions import KeyDownExpression

    return KeyDownExpression(key)


def exists(query: QueryProxy | Query) -> ExistsBuilder:
    """Create an ``exists(query).where(...)`` builder.

    Args:
        query: Query proxy that should be searched.

    Returns:
        A builder whose ``where`` method produces an existence expression.
    """
    from gummysnake.ecs.expressions import ExistsBuilder, QueryProxy

    return ExistsBuilder(cast(QueryProxy, query))


def expression_queries(expr: Expression) -> set[QueryProxy]:
    from gummysnake.ecs.expressions import (
        AttributeExpression,
        BinaryExpression,
        EntityExpression,
        ExistsExpression,
        FieldExpression,
        FunctionExpression,
        GroupedAnyExpression,
        GroupedValueAggregateExpression,
        OuterQueryProvider,
        QueryProxy,
        UnaryExpression,
    )

    def collect(node: Expression) -> set[QueryProxy]:
        if isinstance(node, FieldExpression) and isinstance(node.source, QueryProxy):
            return {node.source}
        if isinstance(node, EntityExpression):
            return {node.query}
        if isinstance(node, BinaryExpression):
            return collect(node.left) | collect(node.right)
        if isinstance(node, UnaryExpression):
            return collect(node.operand)
        if isinstance(node, FunctionExpression):
            refs: set[QueryProxy] = set()
            for arg in node.args:
                refs.update(collect(arg))
            return refs
        if isinstance(node, AttributeExpression):
            return collect(node.base)
        if isinstance(node, GroupedAnyExpression | GroupedValueAggregateExpression):
            return {node.query}
        if isinstance(node, OuterQueryProvider):
            return node._ecs_outer_queries()
        if isinstance(node, ExistsExpression):
            refs = collect(node.predicate)
            refs.discard(node.query)
            return refs
        return set()

    return collect(expr)


def replace_query(expr: Expression, old: QueryProxy, new: QueryProxy) -> Expression:
    """Return ``expr`` with field/entity refs from one query alias replaced by another."""
    from gummysnake.ecs.expressions import (
        AttributeExpression,
        BinaryExpression,
        EntityExpression,
        FieldExpression,
        FunctionExpression,
        UnaryExpression,
    )

    if isinstance(expr, FieldExpression) and expr.source == old:
        return FieldExpression(new, expr.component_type, expr.field_name)
    if isinstance(expr, EntityExpression) and expr.query == old:
        return EntityExpression(new)
    if isinstance(expr, BinaryExpression):
        return BinaryExpression(
            expr.op, replace_query(expr.left, old, new), replace_query(expr.right, old, new)
        )
    if isinstance(expr, UnaryExpression):
        return UnaryExpression(expr.op, replace_query(expr.operand, old, new))
    if isinstance(expr, FunctionExpression):
        return FunctionExpression(
            expr.name, tuple(replace_query(arg, old, new) for arg in expr.args)
        )
    if isinstance(expr, AttributeExpression):
        return AttributeExpression(replace_query(expr.base, old, new), expr.attribute)
    return expr
