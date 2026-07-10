"""Compatibility module for logical-plan UDF declarations."""

from __future__ import annotations

from gummysnake.ecs.logical_plan.actions.udf import (
    RuntimeUdfDefinition,
    UdfCallExpression,
    UdfIterableDefinition,
    udf,
    udf_plan,
    validate_mutation_metadata,
)

__all__ = [
    "RuntimeUdfDefinition",
    "UdfCallExpression",
    "UdfIterableDefinition",
    "udf",
    "udf_plan",
    "validate_mutation_metadata",
]
