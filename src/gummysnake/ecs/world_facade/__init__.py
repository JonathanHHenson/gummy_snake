"""Implementation package for the public :mod:`gummysnake.ecs.world` facade.

``world.py`` remains the authoritative ``EcsWorld`` class. ``initialization``
creates its Python facade metadata only after the required Rust bridge passes
its ABI checks, while ``schema_validation`` discovers dataclass schemas and
registers them with Rust. Entity, resource/event, query, UDF, and physical-plan
operations remain in the focused ``world_runtime`` adapters.
"""

from __future__ import annotations

from gummysnake.ecs.runtime_views import Entity, EntityMutation, EntityView, MutEntity, SystemHandle

from .world import EcsWorld

__all__ = ["EcsWorld", "Entity", "EntityMutation", "EntityView", "MutEntity", "SystemHandle"]
