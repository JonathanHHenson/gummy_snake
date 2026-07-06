"""Compatibility façade for ECS physical-plan payload serialization."""

from __future__ import annotations

from gummysnake.ecs.physical_payload import (
    BRIDGE_PLAN_VERSION,
    PhysicalPlanUnsupported,
    build_physical_payload,
)

__all__ = ["BRIDGE_PLAN_VERSION", "PhysicalPlanUnsupported", "build_physical_payload"]
