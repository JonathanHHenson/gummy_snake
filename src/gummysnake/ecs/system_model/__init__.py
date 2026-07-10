"""Compatibility exports for ECS system definitions and decorators."""

from __future__ import annotations

from gummysnake.ecs.logical_plan.systems import (
    BuiltSystem,
    PlanBuiltSystem,
    RuntimeBuiltSystem,
    RuntimeSystemDefinition,
    SystemDefinition,
    SystemPlanDefinition,
    system,
    system_plan,
)

__all__ = [
    "BuiltSystem",
    "PlanBuiltSystem",
    "RuntimeBuiltSystem",
    "RuntimeSystemDefinition",
    "SystemDefinition",
    "SystemPlanDefinition",
    "system",
    "system_plan",
]
