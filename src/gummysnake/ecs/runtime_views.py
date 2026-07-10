"""ECS runtime view compatibility module."""

from __future__ import annotations

from gummysnake.ecs.runtime_view_model import (
    ComponentView,
    Entity,
    EntityAnnotation,
    EntityMutation,
    EntityView,
    MutEntity,
    ResourceView,
    SystemHandle,
    _copy_stored_value,
    _RuntimeEventWriter,
    _ScheduledSystem,
    _SystemSetConfig,
)

__all__ = [
    "ComponentView",
    "Entity",
    "EntityAnnotation",
    "EntityMutation",
    "EntityView",
    "MutEntity",
    "ResourceView",
    "_copy_stored_value",
    "SystemHandle",
    "_RuntimeEventWriter",
    "_ScheduledSystem",
    "_SystemSetConfig",
]
