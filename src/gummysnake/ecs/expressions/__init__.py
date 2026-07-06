"""Lazy ECS expression objects used by system actions."""

from __future__ import annotations

from gummysnake.ecs.expression_tools import (
    all_of,
    any_of,
    dt,
    ensure_expr,
    exists,
    expression_queries,
    key_is_down,
    literal,
    replace_query,
)
from gummysnake.ecs.expressions.aggregates import (
    ExistsBuilder,
    ExistsExpression,
    GroupedAnyExpression,
    GroupedExpression,
    GroupedValueAggregateExpression,
)
from gummysnake.ecs.expressions.core import (
    AttributeExpression,
    BinaryExpression,
    DeltatimeExpression,
    Expression,
    FunctionExpression,
    KeyDownExpression,
    LiteralExpression,
    OuterQueryProvider,
    UnaryExpression,
    Vector,
)
from gummysnake.ecs.expressions.proxies import (
    ComponentExpressionProxy,
    EntityExpression,
    FieldExpression,
    QueryProxy,
    ResourceProxy,
)

__all__ = [
    "AttributeExpression",
    "BinaryExpression",
    "ComponentExpressionProxy",
    "DeltatimeExpression",
    "EntityExpression",
    "ExistsBuilder",
    "ExistsExpression",
    "Expression",
    "FieldExpression",
    "FunctionExpression",
    "GroupedAnyExpression",
    "GroupedExpression",
    "GroupedValueAggregateExpression",
    "KeyDownExpression",
    "LiteralExpression",
    "OuterQueryProvider",
    "QueryProxy",
    "ResourceProxy",
    "UnaryExpression",
    "Vector",
    "all_of",
    "any_of",
    "dt",
    "ensure_expr",
    "exists",
    "expression_queries",
    "key_is_down",
    "literal",
    "replace_query",
]
