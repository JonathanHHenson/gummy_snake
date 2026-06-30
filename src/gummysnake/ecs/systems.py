"""ECS system decorators and system registration helpers."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import get_type_hints, overload

from gummysnake.ecs.actions import Action, SystemPlan
from gummysnake.ecs.expressions import QueryProxy, ResourceProxy
from gummysnake.ecs.specs import (
    EventReaderProxy,
    EventSpec,
    EventWriterProxy,
    QuerySpec,
    ResourceSpec,
)
from gummysnake.exceptions import SystemPlanError


@dataclass(frozen=True)
class SystemDefinition:
    """Decorated system builder function."""

    function: Callable[..., Action]
    name: str | None = None

    @property
    def display_name(self) -> str:
        return self.name or self.function.__name__

    def build(self) -> BuiltSystem:
        signature = inspect.signature(self.function)
        hints = get_type_hints(self.function, include_extras=True)
        args: list[object] = []
        query_proxies: list[QueryProxy] = []
        resource_proxies: list[ResourceProxy] = []
        event_proxies: list[EventReaderProxy | EventWriterProxy] = []
        for parameter in signature.parameters.values():
            annotation = hints.get(parameter.name)
            if annotation is None:
                raise SystemPlanError(
                    f"ECS system {self.function.__name__} parameter {parameter.name!r} "
                    "needs an ecs.Query, ecs.Res, or ecs.ResMut annotation."
                )
            if isinstance(annotation, QuerySpec):
                query_proxy = QueryProxy(parameter.name, annotation)
                query_proxies.append(query_proxy)
                args.append(query_proxy)
            elif isinstance(annotation, ResourceSpec):
                resource_proxy = ResourceProxy(
                    parameter.name, annotation.resource_type, annotation.mutable
                )
                resource_proxies.append(resource_proxy)
                args.append(resource_proxy)
            elif isinstance(annotation, EventSpec):
                event_proxy: EventReaderProxy | EventWriterProxy
                if annotation.mode == "reader":
                    event_proxy = EventReaderProxy(parameter.name, annotation.event_type)
                else:
                    event_proxy = EventWriterProxy(parameter.name, annotation.event_type)
                event_proxies.append(event_proxy)
                args.append(event_proxy)
            else:
                raise SystemPlanError(
                    f"Unsupported ECS system annotation for {parameter.name!r}: {annotation!r}."
                )
        result = self.function(*args)
        if isinstance(result, SystemPlan):
            raise SystemPlanError(
                f"ECS system {self.function.__name__} returned SystemPlan. "
                "Return the complete ecs.Action instead; the registry calls Action.plan()."
            )
        if not isinstance(result, Action):
            raise SystemPlanError(
                f"ECS system {self.function.__name__} must return ecs.Action, "
                f"got {type(result).__name__}."
            )
        return BuiltSystem(
            definition=self,
            plan=result.plan(),
            queries=tuple(query_proxies),
            resources=tuple(resource_proxies),
            events=tuple(event_proxies),
        )

    def explain(self) -> str:
        return self.build().plan.explain()


@dataclass(frozen=True)
class BuiltSystem:
    definition: SystemDefinition
    plan: SystemPlan
    queries: tuple[QueryProxy, ...]
    resources: tuple[ResourceProxy, ...]
    events: tuple[EventReaderProxy | EventWriterProxy, ...] = ()

    @property
    def name(self) -> str:
        return self.definition.name or self.definition.function.__name__


@overload
def system(function: Callable[..., Action], /) -> SystemDefinition: ...


@overload
def system(
    function: None = None, *, name: str | None = None
) -> Callable[[Callable[..., Action]], SystemDefinition]: ...


def system(
    function: Callable[..., Action] | None = None, *, name: str | None = None
) -> SystemDefinition | Callable[[Callable[..., Action]], SystemDefinition]:
    """Decorate a function as an ECS system builder."""

    def decorate(callback: Callable[..., Action]) -> SystemDefinition:
        return SystemDefinition(callback, name=name)

    if function is not None:
        return decorate(function)
    return decorate


__all__ = ["BuiltSystem", "SystemDefinition", "system"]
