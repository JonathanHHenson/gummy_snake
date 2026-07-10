"""Compatibility module for lazy ECS expression proxies."""

from __future__ import annotations

from gummysnake.ecs.logical_plan.expressions.proxies import (
    ComponentExpressionProxy,
    EntityExpression,
    FieldExpression,
    QueryProxy,
    ResourceProxy,
)

__all__ = [
    "ComponentExpressionProxy",
    "EntityExpression",
    "FieldExpression",
    "QueryProxy",
    "ResourceProxy",
]
