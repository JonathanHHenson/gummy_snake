"""Pythonic ECS API for Gummy Snake."""

from __future__ import annotations

from gummysnake.ecs import spatial, types
from gummysnake.ecs.actions import (
    Action,
    DefaultAction,
    ForEachAction,
    SystemPlan,
    UdfDefinition,
    WhenAction,
    do,
    do_in_order,
    do_in_parallel,
    emit_event,
    for_each,
    set,
    udf,
    when,
)
from gummysnake.ecs.expressions import (
    Expression,
    all_of,
    any_of,
    dt,
    exists,
    key_is_down,
    literal,
)
from gummysnake.ecs.specs import (
    Added,
    Changed,
    EventReader,
    EventWriter,
    Query,
    Removed,
    Res,
    ResMut,
    Tag,
)
from gummysnake.ecs.systems import SystemDefinition, system
from gummysnake.ecs.world import Entity, EntityView, MutEntity, SystemHandle

__all__ = [
    "Action",
    "Added",
    "Changed",
    "DefaultAction",
    "Entity",
    "EntityView",
    "EventReader",
    "EventWriter",
    "Expression",
    "ForEachAction",
    "MutEntity",
    "Query",
    "Removed",
    "Res",
    "ResMut",
    "SystemDefinition",
    "SystemHandle",
    "SystemPlan",
    "Tag",
    "UdfDefinition",
    "WhenAction",
    "all_of",
    "any_of",
    "do",
    "do_in_order",
    "do_in_parallel",
    "dt",
    "emit_event",
    "exists",
    "for_each",
    "key_is_down",
    "literal",
    "set",
    "spatial",
    "system",
    "types",
    "udf",
    "when",
]
