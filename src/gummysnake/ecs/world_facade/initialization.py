"""Initialize the Python metadata that accompanies one Rust-owned ECS world.

This module owns only Python facade state. ``create_ecs_world()`` performs the
mandatory canvas/ECS ABI validation and creates the canonical Rust storage
before the facade exposes entity, resource, event, or system operations.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from gummysnake.rust.ecs import create_ecs_world

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.context import SketchContext
    from gummysnake.ecs.world_facade.world import EcsWorld


def initialize_world(world: EcsWorld, context: SketchContext | None) -> None:
    """Initialize facade metadata around a newly validated Rust ECS world.

    Component columns, resources, events, entity generations, spatial indexes,
    and compiled physical plans remain in the Rust runtime. The attributes here
    are Python API metadata, diagnostics, scheduling configuration, and
    frame-local change bookkeeping only.
    """

    world.context = context
    world._world_id = id(world)
    world._rust = create_ecs_world()
    world._systems = []
    world._system_sets = {}
    world._group_orders = []
    world._next_system_id = 1
    world.strict = False
    world.warn_on_ambiguity = True
    world._diagnostics = Counter()
    world._schemas = {}
    world._spatial_epoch = 0
    world._spatial_index_cache = {}
    world._spatial_relation_cache = {}
    world._spatial_aggregate_cache = {}
    world._expression_eval_cache = {}
    world._defer_spatial_invalidation = False
    world._spatial_invalidated_deferred = False
    world._ecs_frame = 0
    world._added_components = set()
    world._changed_components = set()
    world._removed_components = set()
    world._event_types = {}
    world._has_change_filtered_systems_cache = None
    world._active_python_access_batch = None
