"""Canonical implementation package for ECS runtime views and handles.

This package groups the runtime-view implementations while preserving explicit
ownership and stable ``__module__`` metadata:

- :mod:`entity_mutation` owns immutable entity handles and explicit Python-UDF
  mutation annotations;
- :mod:`component_resource_views` owns Rust-backed component/resource field
  accessors;
- :mod:`runtime_handles` owns entity views, event writers, and system handles.

Views may cache access only within an explicit Python UDF/system boundary. They
always read from and write to the Rust ECS bridge; this package owns no component
columns or alternate world state.
"""

from __future__ import annotations

from gummysnake.ecs.runtime_view_model.component_resource_views import ComponentView, ResourceView
from gummysnake.ecs.runtime_view_model.entity_mutation import (
    Entity,
    EntityAnnotation,
    EntityMutation,
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
    "ResourceView",
    "SystemHandle",
    "_RuntimeEventWriter",
    "_ScheduledSystem",
    "_SystemSetConfig",
    "_copy_stored_value",
]
