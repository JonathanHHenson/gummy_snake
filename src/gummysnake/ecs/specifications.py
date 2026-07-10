"""Compatibility exports for ECS logical-plan annotations and event proxies."""

from __future__ import annotations

from gummysnake.ecs.specs import (
    Added,
    Changed,
    ChangeTerm,
    EventReader,
    EventReaderProxy,
    EventSpec,
    EventWriter,
    EventWriterProxy,
    Query,
    QuerySpec,
    Removed,
    Res,
    ResMut,
    ResourceSpec,
    Tag,
    TagTerm,
    Without,
    WithoutTerm,
)

__all__ = [
    "Added",
    "ChangeTerm",
    "Changed",
    "EventReader",
    "EventReaderProxy",
    "EventSpec",
    "EventWriter",
    "EventWriterProxy",
    "Query",
    "QuerySpec",
    "Removed",
    "Res",
    "ResMut",
    "ResourceSpec",
    "Tag",
    "TagTerm",
    "Without",
    "WithoutTerm",
]
