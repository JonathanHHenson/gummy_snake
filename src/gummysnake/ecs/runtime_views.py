"""ECS runtime view compatibility module."""

from __future__ import annotations

from gummysnake.ecs.runtime_view_model.component_resource_views import ComponentView, ResourceView
from gummysnake.ecs.runtime_view_model.entity_mutation import (
    Entity,
    EntityAnnotation,
    EntityMutation,
    MutEntity,
    _copy_stored_value,
)
from gummysnake.ecs.runtime_view_model.runtime_handles import (
    EntityView,
    SystemHandle,
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
