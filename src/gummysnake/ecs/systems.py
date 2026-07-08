"""ECS system decorators and system registration helpers."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import get_type_hints, overload

from gummysnake.ecs.actions import Action, SystemPlan, build_session, validate_mutation_metadata
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
    """Decorated ECS system function."""

    function: Callable[..., object]
    name: str | None = None
    parallel: bool = False
    python: bool = False
    queries: Mapping[str, object] = field(default_factory=dict)
    mutations: Mapping[str, object] = field(default_factory=dict)
    group: str | Iterable[str] | None = None
    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()

    @property
    def display_name(self) -> str:
        """Return the scheduler name shown in diagnostics and explain output.

        Returns:
            The explicit system name, or the decorated function name when no name was given.
        """

        return self.name or self.function.__name__

    def build(self) -> BuiltSystem:
        """Build the logical ECS plan recorded by this system function.

        Returns:
            A built system containing query/resource/event proxies and a serializable plan.
        """

        signature = inspect.signature(self.function)
        hints = get_type_hints(self.function, include_extras=True)
        args: list[object] = []
        query_proxies: list[QueryProxy] = []
        resource_proxies: list[ResourceProxy] = []
        event_proxies: list[EventReaderProxy | EventWriterProxy] = []
        for parameter in signature.parameters.values():
            annotation = hints.get(parameter.name)
            if annotation is None:
                if self.python:
                    args.append(None)
                    continue
                raise SystemPlanError(
                    f"ECS system {self.function.__name__} parameter {parameter.name!r} "
                    "needs an ecs.Query, ecs.Res, ecs.ResMut, ecs.EventReader, or "
                    "ecs.EventWriter annotation."
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
            elif self.python:
                args.append(None)
            else:
                raise SystemPlanError(
                    f"Unsupported ECS system annotation for {parameter.name!r}: {annotation!r}."
                )
        if self.python:
            return BuiltSystem(
                definition=self,
                plan=_noop_plan(),
                queries=tuple(query_proxies),
                resources=tuple(resource_proxies),
                events=tuple(event_proxies),
                python=True,
            )

        with build_session(parallel=self.parallel) as session:
            result = self.function(*args)
            if isinstance(result, SystemPlan):
                raise SystemPlanError(
                    f"ECS system {self.function.__name__} returned SystemPlan. "
                    "Context-managed ECS systems must return None; use field.set_to(...), "
                    "field.increase_by(...), with ecs.conditional():/ecs.when():, and "
                    "with ecs.do: blocks to record actions."
                )
            if isinstance(result, Action):
                raise SystemPlanError(
                    f"ECS system {self.function.__name__} returned an ecs.Action. "
                    "The return-action ECS authoring style has been replaced by context-managed "
                    "systems. For example, replace return ecs.set(pos.x, value) with "
                    "pos.x.set_to(value), and replace ecs.when(...).do(...) with "
                    "with ecs.conditional():\n    with ecs.when(...):\n        field.set_to(...)."
                )
            if result is not None:
                raise SystemPlanError(
                    f"Rust-executed ECS system {self.function.__name__} must return None, "
                    f"got {type(result).__name__}. Use @ecs.system(python=True) for explicit "
                    "runtime Python systems."
                )
            action = session.finish()
        return BuiltSystem(
            definition=self,
            plan=action.plan(),
            queries=tuple(query_proxies),
            resources=tuple(resource_proxies),
            events=tuple(event_proxies),
            python=False,
        )

    def explain(self) -> str:
        """Describe the system plan in beginner-readable text.

        Returns:
            Multiline text showing the actions the ECS planner will execute.
        """

        return self.build().plan.explain()


@dataclass(frozen=True)
class BuiltSystem:
    """Compiled ECS system metadata ready for registration with an ``EcsWorld``."""

    definition: SystemDefinition
    plan: SystemPlan
    queries: tuple[QueryProxy, ...]
    resources: tuple[ResourceProxy, ...]
    events: tuple[EventReaderProxy | EventWriterProxy, ...] = ()
    python: bool = False

    @property
    def name(self) -> str:
        """Return the system name used by the scheduler.

        Returns:
            The explicit system name, or the decorated function name when no name was given.
        """

        return self.definition.name or self.definition.function.__name__


def _noop_plan() -> SystemPlan:
    from gummysnake.ecs.actions import DefaultAction

    return DefaultAction("noop").plan()


@overload
def system(function: Callable[..., object], /) -> SystemDefinition: ...


@overload
def system(
    function: Callable[..., object],
    /,
    *,
    name: str | None = None,
    parallel: bool = False,
    python: bool = False,
    queries: Mapping[str, object] | None = None,
    mutations: Mapping[str, object] | None = None,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> SystemDefinition: ...


@overload
def system(
    function: None = None,
    *,
    name: str | None = None,
    parallel: bool = False,
    python: bool = False,
    queries: Mapping[str, object] | None = None,
    mutations: Mapping[str, object] | None = None,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> Callable[[Callable[..., object]], SystemDefinition]: ...


def system(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    parallel: bool = False,
    python: bool = False,
    queries: Mapping[str, object] | None = None,
    mutations: Mapping[str, object] | None = None,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> SystemDefinition | Callable[[Callable[..., object]], SystemDefinition]:
    """Decorate a function as an ECS system.

    Rust-executed systems (the default) run once at registration to record a
    context-managed logical plan and must return ``None``. ``python=True`` opts
    into runtime Python execution explicitly and never acts as a fallback for
    invalid Rust plans.

    Args:
        function: Function to decorate when ``@ecs.system`` is used without parentheses.
        name: Optional scheduler name to show in diagnostics instead of the function name.
        parallel: Whether Rust may execute independent recorded actions in parallel.
        python: Run this system as an explicit Python runtime boundary.
        queries: Query metadata for unannotated parameters in Python systems.
        mutations: Entity mutation metadata for Python systems.
        group: Optional system group name or sequence of group names. Group names are
            validated at registration.
        before: Group names that this system's implicit group should run before.
        after: Group names that this system's implicit group should run after.

    Returns:
        A system definition, or a decorator that creates one.
    """

    if python and parallel:
        raise SystemPlanError(
            "@ecs.system(python=True) is a scheduler barrier; parallel=True is invalid."
        )
    normalized_before = tuple(str(item) for item in before)
    normalized_after = tuple(str(item) for item in after)
    if group is not None and (normalized_before or normalized_after):
        raise SystemPlanError(
            "@ecs.system(group=...) cannot also declare before=... or after=...; "
            "configure group order with gs.group() or gs.order()."
        )

    def decorate(callback: Callable[..., object]) -> SystemDefinition:
        if not python and queries:
            raise SystemPlanError(
                "@ecs.system queries={...} metadata is only valid with @ecs.system(python=True)."
            )
        if not python and mutations:
            raise SystemPlanError(
                "@ecs.system mutations={...} metadata is only valid with @ecs.system(python=True)."
            )
        normalized_queries = _validate_query_metadata(callback, queries) if python else {}
        normalized_mutations = validate_mutation_metadata(callback, mutations) if python else {}
        return SystemDefinition(
            callback,
            name=name,
            parallel=bool(parallel),
            python=bool(python),
            queries=normalized_queries,
            mutations=normalized_mutations,
            group=group,
            before=normalized_before,
            after=normalized_after,
        )

    if function is not None:
        return decorate(function)
    return decorate


def _validate_query_metadata(
    callback: Callable[..., object], queries: Mapping[str, object] | None
) -> dict[str, QuerySpec]:
    if not queries:
        return {}
    parameter_names = set(inspect.signature(callback).parameters)
    normalized: dict[str, QuerySpec] = {}
    for parameter_name, query in queries.items():
        if parameter_name not in parameter_names:
            raise SystemPlanError(
                f"Python ECS system query metadata for {callback.__name__} references "
                f"unknown parameter {parameter_name!r}."
            )
        if not isinstance(query, QuerySpec):
            raise SystemPlanError(
                f"Python ECS system query metadata for {parameter_name!r} must be ecs.Query[...]."
            )
        normalized[parameter_name] = query
    return normalized


__all__ = ["BuiltSystem", "SystemDefinition", "system"]
