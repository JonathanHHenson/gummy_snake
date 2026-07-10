"""Compatibility exports for logical-plan action analysis."""

from __future__ import annotations

from gummysnake.ecs.logical_plan.inspection.analysis import action_query_refs, action_write_targets

__all__ = ["action_query_refs", "action_write_targets"]
