"""Runtime annotation helpers for ECS queries, tags, and resources."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from gummysnake.ecs.expressions import ComponentExpressionProxy, QueryProxy


@dataclass(frozen=True)
class TagTerm:
    value: object


@dataclass(frozen=True)
class ChangeTerm:
    kind: str
    component_type: type[Any]


@dataclass(frozen=True)
class WithoutTerm:
    value: object


class Changed:
    """Query annotation marker for entities whose component changed this frame."""

    def __class_getitem__(cls, item: type[Any]) -> ChangeTerm:
        return ChangeTerm("changed", item)


class Added:
    """Query annotation marker for entities whose component was added this frame."""

    def __class_getitem__(cls, item: type[Any]) -> ChangeTerm:
        return ChangeTerm("added", item)


class Removed:
    """Query annotation marker for entities whose component was removed this frame."""

    def __class_getitem__(cls, item: type[Any]) -> ChangeTerm:
        return ChangeTerm("removed", item)


class Tag:
    """Annotation marker for a zero-sized tag query term."""

    def __class_getitem__(cls, item: object) -> TagTerm:
        return TagTerm(item)


class Without:
    """Query annotation marker excluding a component type or tag term."""

    def __class_getitem__(cls, item: object) -> WithoutTerm:
        if isinstance(item, tuple):
            raise TypeError("ecs.Without[...] accepts one component type or ecs.Tag[...] term.")
        return WithoutTerm(item)


@dataclass(frozen=True)
class QuerySpec:
    terms: tuple[object, ...]


class Query:
    """Annotation marker for a system entity query."""

    def __class_getitem__(cls, item: object) -> QuerySpec:
        terms = item if isinstance(item, tuple) else (item,)
        return QuerySpec(tuple(terms))

    @property
    def ctx(self) -> QueryProxy:
        raise TypeError("ecs.Query is an annotation marker; systems receive query proxies.")

    def __getitem__(self, component_type: type[Any]) -> ComponentExpressionProxy:
        raise TypeError("ecs.Query is an annotation marker; systems receive query proxies.")

    def __iter__(self) -> Iterator[Any]:
        raise TypeError(
            "ecs.Query is an annotation marker; explicit Python systems receive entity views."
        )


@dataclass(frozen=True)
class ResourceSpec:
    resource_type: type[Any]
    mutable: bool = False


@dataclass(frozen=True)
class EventSpec:
    event_type: type[Any]
    mode: str


@dataclass(frozen=True)
class EventReaderProxy:
    name: str
    event_type: type[Any]


@dataclass(frozen=True)
class EventWriterProxy:
    name: str
    event_type: type[Any]

    def emit(self, event: object) -> None:
        """Queue an event from inside an ECS system build block.

        Args:
            event: Event instance matching this writer's event type.
        """

        from gummysnake.ecs.actions import append_action, emit_event
        from gummysnake.exceptions import SystemPlanError

        if type(event) is not self.event_type:
            raise SystemPlanError(
                f"Expected ECS event {self.event_type.__name__}, got {type(event).__name__}."
            )
        append_action(emit_event(self, event), operation=f"{self.name}.emit()")


class Res:
    """Annotation marker for read-only ECS resource access."""

    def __class_getitem__(cls, item: type[Any]) -> ResourceSpec:
        return ResourceSpec(item, mutable=False)

    def __getitem__(self, resource_type: type[Any]) -> ComponentExpressionProxy:
        raise TypeError("ecs.Res is an annotation marker; systems receive resource proxies.")


class EventReader:
    """Annotation marker for deterministic typed ECS event reads."""

    def __class_getitem__(cls, item: type[Any]) -> EventSpec:
        return EventSpec(item, "reader")


class EventWriter:
    """Annotation marker for deterministic typed ECS event writes."""

    def __class_getitem__(cls, item: type[Any]) -> EventSpec:
        return EventSpec(item, "writer")

    def emit(self, event: object) -> None:
        del event
        raise TypeError("ecs.EventWriter is an annotation marker; systems receive writer proxies.")


class ResMut:
    """Annotation marker for mutable ECS resource access."""

    def __class_getitem__(cls, item: type[Any]) -> ResourceSpec:
        return ResourceSpec(item, mutable=True)

    def __getitem__(self, resource_type: type[Any]) -> ComponentExpressionProxy:
        raise TypeError("ecs.ResMut is an annotation marker; systems receive resource proxies.")


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
