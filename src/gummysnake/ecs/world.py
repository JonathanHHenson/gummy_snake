"""ECS world facade compatibility module."""

from __future__ import annotations

from gummysnake.ecs.runtime_views import Entity, EntityMutation, EntityView, MutEntity, SystemHandle
from gummysnake.ecs.world_facade import EcsWorld

__all__ = ["EcsWorld", "Entity", "EntityMutation", "EntityView", "MutEntity", "SystemHandle"]
