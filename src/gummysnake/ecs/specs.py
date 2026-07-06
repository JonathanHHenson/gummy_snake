"""Runtime annotation helpers for ECS queries, tags, and resources."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from gummysnake.ecs.expressions import ComponentExpressionProxy, QueryProxy


@dataclass(frozen=True)
class TagTerm:
    """Query term that matches entities carrying one tag value."""

    value: object


@dataclass(frozen=True)
class ChangeTerm:
    """Query term that filters entities by component change state."""

    kind: str
    component_type: type[Any]


@dataclass(frozen=True)
class WithoutTerm:
    """Query term that excludes entities with a component or tag."""

    value: object


class Changed:
    """Query annotation marker for entities whose component changed this frame."""

    def __class_getitem__(cls, item: type[Any]) -> ChangeTerm:
        """Create a query term for components changed since the previous frame.

        Args:
            item: Component type whose changed rows should match.

        Returns:
            A query term consumed by ``ecs.Query[...]``.
        """

        return ChangeTerm("changed", item)


class Added:
    """Query annotation marker for entities whose component was added this frame."""

    def __class_getitem__(cls, item: type[Any]) -> ChangeTerm:
        """Create a query term for components added this frame.

        Args:
            item: Component type whose newly added rows should match.

        Returns:
            A query term consumed by ``ecs.Query[...]``.
        """

        return ChangeTerm("added", item)


class Removed:
    """Query annotation marker for entities whose component was removed this frame."""

    def __class_getitem__(cls, item: type[Any]) -> ChangeTerm:
        """Create a query term for components removed this frame.

        Args:
            item: Component type whose removed rows should match.

        Returns:
            A query term consumed by ``ecs.Query[...]``.
        """

        return ChangeTerm("removed", item)


class Tag:
    """Annotation marker for a zero-sized tag query term."""

    def __class_getitem__(cls, item: object) -> TagTerm:
        """Create a query term that requires a tag.

        Args:
            item: Tag value that matching entities must have.

        Returns:
            A query term consumed by ``ecs.Query[...]``.
        """

        return TagTerm(item)


class Without:
    """Query annotation marker excluding a component type or tag term."""

    def __class_getitem__(cls, item: object) -> WithoutTerm:
        """Create a query term that rejects entities with a component or tag.

        Args:
            item: Component type or ``ecs.Tag[...]`` term to exclude.

        Returns:
            A query term consumed by ``ecs.Query[...]``.
        """

        if isinstance(item, tuple):
            raise TypeError("ecs.Without[...] accepts one component type or ecs.Tag[...] term.")
        return WithoutTerm(item)


@dataclass(frozen=True)
class QuerySpec:
    """Stored component, tag, and filter terms from ``ecs.Query[...]``."""

    terms: tuple[object, ...]


class Query:
    """Annotation marker for a system entity query."""

    def __class_getitem__(cls, item: object) -> QuerySpec:
        """Create a query annotation for system parameters.

        Args:
            item: Component types, tag terms, or filter terms to match.

        Returns:
            A query specification consumed when the system is planned.
        """

        terms = item if isinstance(item, tuple) else (item,)
        return QuerySpec(tuple(terms))

    @property
    def ctx(self) -> QueryProxy:
        """Explain that runtime query proxies are only created for system parameters."""

        raise TypeError("ecs.Query is an annotation marker; systems receive query proxies.")

    def __getitem__(self, component_type: type[Any]) -> ComponentExpressionProxy:
        """Explain that component fields are read from system query proxies.

        Args:
            component_type: Component type requested with subscription syntax.

        Returns:
            This method always raises because ``ecs.Query`` is only an annotation marker.
        """

        raise TypeError("ecs.Query is an annotation marker; systems receive query proxies.")

    def __iter__(self) -> Iterator[Any]:
        """Explain that query rows are materialized only inside explicit Python systems.

        Returns:
            This method always raises because ``ecs.Query`` is only an annotation marker.
        """

        raise TypeError(
            "ecs.Query is an annotation marker; explicit Python systems receive entity views."
        )


@dataclass(frozen=True)
class ResourceSpec:
    """Stored resource type and mutability from ``ecs.Res[...]`` annotations."""

    resource_type: type[Any]
    mutable: bool = False


@dataclass(frozen=True)
class EventSpec:
    """Stored event type and reader/writer mode from event annotations."""

    event_type: type[Any]
    mode: str


@dataclass(frozen=True)
class EventReaderProxy:
    """System parameter proxy used to read typed ECS events."""

    name: str
    event_type: type[Any]


@dataclass(frozen=True)
class EventWriterProxy:
    """System parameter proxy used to emit typed ECS events."""

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
        """Create a read-only resource annotation for a system parameter.

        Args:
            item: Resource dataclass type the system may read.

        Returns:
            A resource specification consumed when the system is planned.
        """

        return ResourceSpec(item, mutable=False)

    def __getitem__(self, resource_type: type[Any]) -> ComponentExpressionProxy:
        """Explain that resource fields are read from system resource proxies.

        Args:
            resource_type: Resource type requested with subscription syntax.

        Returns:
            This method always raises because ``ecs.Res`` is only an annotation marker.
        """

        raise TypeError("ecs.Res is an annotation marker; systems receive resource proxies.")


class EventReader:
    """Annotation marker for deterministic typed ECS event reads."""

    def __class_getitem__(cls, item: type[Any]) -> EventSpec:
        """Create an event-reader annotation for a system parameter.

        Args:
            item: Event dataclass type the system may read.

        Returns:
            An event specification consumed when the system is planned.
        """

        return EventSpec(item, "reader")


class EventWriter:
    """Annotation marker for deterministic typed ECS event writes."""

    def __class_getitem__(cls, item: type[Any]) -> EventSpec:
        """Create an event-writer annotation for a system parameter.

        Args:
            item: Event dataclass type the system may emit.

        Returns:
            An event specification consumed when the system is planned.
        """

        return EventSpec(item, "writer")

    def emit(self, event: object) -> None:
        """Explain that events are emitted from system event-writer proxies.

        Args:
            event: Event value a caller attempted to emit from the marker itself.
        """

        del event
        raise TypeError("ecs.EventWriter is an annotation marker; systems receive writer proxies.")


class ResMut:
    """Annotation marker for mutable ECS resource access."""

    def __class_getitem__(cls, item: type[Any]) -> ResourceSpec:
        """Create a mutable resource annotation for a system parameter.

        Args:
            item: Resource dataclass type the system may read and write.

        Returns:
            A resource specification consumed when the system is planned.
        """

        return ResourceSpec(item, mutable=True)

    def __getitem__(self, resource_type: type[Any]) -> ComponentExpressionProxy:
        """Explain that resource fields are read from system resource proxies.

        Args:
            resource_type: Resource type requested with subscription syntax.

        Returns:
            This method always raises because ``ecs.ResMut`` is only an annotation marker.
        """

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
