"""Compatibility module for logical-plan action nodes."""

from __future__ import annotations

from gummysnake.ecs.logical_plan.actions.nodes import (
    Action,
    DefaultAction,
    EntityIteratorSource,
    EventIterableSource,
    ExpressionIterableSource,
    ForEachAction,
    IterableSource,
    LoopItem,
    SystemPlan,
    UdfArgument,
    UdfDefinition,
    UdfIterableSource,
    UdfPlanDefinition,
    WhenAction,
    _RuntimeUdfBase,
)

__all__ = [
    "Action",
    "DefaultAction",
    "EntityIteratorSource",
    "EventIterableSource",
    "ExpressionIterableSource",
    "ForEachAction",
    "IterableSource",
    "LoopItem",
    "SystemPlan",
    "UdfArgument",
    "UdfDefinition",
    "UdfIterableSource",
    "UdfPlanDefinition",
    "WhenAction",
    "_RuntimeUdfBase",
]
