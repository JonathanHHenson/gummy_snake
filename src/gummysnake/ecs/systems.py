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
    """Base metadata for a decorated ECS system function."""

    function: Callable[..., object]
    name: str | None = None
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
        """Build metadata for scheduling this system."""

        raise NotImplementedError

    def explain(self) -> str:
        """Describe the system plan in beginner-readable text.

        Returns:
            Multiline text showing the actions the ECS planner will execute.
        """

        return self.build().plan.explain()


@dataclass(frozen=True)
class RuntimeSystemDefinition(SystemDefinition):
    """Decorated runtime Python ECS system function."""

    queries: Mapping[str, object] = field(default_factory=dict)
    mutations: Mapping[str, object] = field(default_factory=dict)

    def build(self) -> RuntimeBuiltSystem:
        """Build runtime Python system metadata without executing the callback."""

        args, query_proxies, resource_proxies, event_proxies = _system_proxy_args(
            self.function,
            allow_runtime_values=True,
        )
        del args
        return RuntimeBuiltSystem(
            definition=self,
            plan=_noop_plan(),
            queries=tuple(query_proxies),
            resources=tuple(resource_proxies),
            events=tuple(event_proxies),
        )


@dataclass(frozen=True)
class SystemPlanDefinition(SystemDefinition):
    """Decorated Rust-executed ECS system plan function."""

    parallel: bool = False

    def build(self) -> PlanBuiltSystem:
        """Build the logical ECS plan recorded by this system function.

        Returns:
            A built system containing query/resource/event proxies and a serializable plan.
        """

        args, query_proxies, resource_proxies, event_proxies = _system_proxy_args(
            self.function,
            allow_runtime_values=False,
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
                    f"Rust-executed ECS system plan {self.function.__name__} must return None, "
                    f"got {type(result).__name__}. Use @ecs.system for runtime Python systems."
                )
            action = session.finish()
        return PlanBuiltSystem(
            definition=self,
            plan=action.plan(),
            queries=tuple(query_proxies),
            resources=tuple(resource_proxies),
            events=tuple(event_proxies),
        )


@dataclass(frozen=True)
class BuiltSystem:
    """Compiled ECS system metadata ready for registration with an ``EcsWorld``."""

    definition: SystemDefinition
    plan: SystemPlan
    queries: tuple[QueryProxy, ...]
    resources: tuple[ResourceProxy, ...]
    events: tuple[EventReaderProxy | EventWriterProxy, ...] = ()

    @property
    def name(self) -> str:
        """Return the system name used by the scheduler.

        Returns:
            The explicit system name, or the decorated function name when no name was given.
        """

        return self.definition.name or self.definition.function.__name__


@dataclass(frozen=True)
class RuntimeBuiltSystem(BuiltSystem):
    """Built metadata for a runtime Python ECS system."""

    definition: RuntimeSystemDefinition


@dataclass(frozen=True)
class PlanBuiltSystem(BuiltSystem):
    """Built metadata for a Rust-executed ECS system plan."""

    definition: SystemPlanDefinition


def _noop_plan() -> SystemPlan:
    from gummysnake.ecs.actions import DefaultAction

    return DefaultAction("noop").plan()


def _system_proxy_args(
    callback: Callable[..., object],
    *,
    allow_runtime_values: bool,
) -> tuple[
    list[object],
    list[QueryProxy],
    list[ResourceProxy],
    list[EventReaderProxy | EventWriterProxy],
]:
    signature = inspect.signature(callback)
    hints = get_type_hints(callback, include_extras=True)
    args: list[object] = []
    query_proxies: list[QueryProxy] = []
    resource_proxies: list[ResourceProxy] = []
    event_proxies: list[EventReaderProxy | EventWriterProxy] = []
    for parameter in signature.parameters.values():
        annotation = hints.get(parameter.name)
        if annotation is None:
            if allow_runtime_values:
                args.append(None)
                continue
            raise SystemPlanError(
                f"ECS system {callback.__name__} parameter {parameter.name!r} "
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
        elif allow_runtime_values:
            args.append(None)
        else:
            raise SystemPlanError(
                f"Unsupported ECS system annotation for {parameter.name!r}: {annotation!r}."
            )
    return args, query_proxies, resource_proxies, event_proxies


@overload
def system(function: Callable[..., object], /) -> RuntimeSystemDefinition: ...


@overload
def system(
    function: Callable[..., object],
    /,
    *,
    name: str | None = None,
    queries: Mapping[str, object] | None = None,
    mutations: Mapping[str, object] | None = None,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> RuntimeSystemDefinition: ...


@overload
def system(
    function: None = None,
    *,
    name: str | None = None,
    queries: Mapping[str, object] | None = None,
    mutations: Mapping[str, object] | None = None,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> Callable[[Callable[..., object]], RuntimeSystemDefinition]: ...


def system(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    queries: Mapping[str, object] | None = None,
    mutations: Mapping[str, object] | None = None,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> RuntimeSystemDefinition | Callable[[Callable[..., object]], RuntimeSystemDefinition]:
    """Decorate a function as a runtime Python ECS system.

    Python systems execute during the ECS schedule as explicit scheduler
    barriers. Use :func:`system_plan` for Rust-executed logical plans.

    Args:
        function: Function to decorate when ``@ecs.system`` is used without parentheses.
        name: Optional scheduler name to show in diagnostics instead of the function name.
        queries: Query metadata for unannotated parameters in Python systems.
        mutations: Entity mutation metadata for Python systems.
        group: Optional system group name or sequence of group names. Group names are
            validated at registration.
        before: Group names that this system's implicit group should run before.
        after: Group names that this system's implicit group should run after.

    Returns:
        A system definition, or a decorator that creates one.
    """

    normalized_before, normalized_after = _normalize_scheduling("@ecs.system", group, before, after)

    def decorate(callback: Callable[..., object]) -> RuntimeSystemDefinition:
        return RuntimeSystemDefinition(
            callback,
            name=name,
            group=group,
            before=normalized_before,
            after=normalized_after,
            queries=_validate_query_metadata(callback, queries),
            mutations=validate_mutation_metadata(callback, mutations),
        )

    if function is not None:
        return decorate(function)
    return decorate


@overload
def system_plan(function: Callable[..., object], /) -> SystemPlanDefinition: ...


@overload
def system_plan(
    function: Callable[..., object],
    /,
    *,
    name: str | None = None,
    parallel: bool = False,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> SystemPlanDefinition: ...


@overload
def system_plan(
    function: None = None,
    *,
    name: str | None = None,
    parallel: bool = False,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> Callable[[Callable[..., object]], SystemPlanDefinition]: ...


def system_plan(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    parallel: bool = False,
    group: str | Iterable[str] | None = None,
    before: Iterable[str] = (),
    after: Iterable[str] = (),
) -> SystemPlanDefinition | Callable[[Callable[..., object]], SystemPlanDefinition]:
    """Decorate a function as a Rust-executed ECS logical plan.

    Plan systems run once at registration to record context-managed ECS actions.
    They execute later through the Rust physical-plan runtime and must return
    ``None``. Use :func:`system` for runtime Python systems.

    Args:
        function: Function to decorate when ``@ecs.system_plan`` is used without parentheses.
        name: Optional scheduler name to show in diagnostics instead of the function name.
        parallel: Whether Rust may execute independent recorded actions in parallel.
        group: Optional system group name or sequence of group names. Group names are
            validated at registration.
        before: Group names that this system's implicit group should run before.
        after: Group names that this system's implicit group should run after.

    Returns:
        A system definition, or a decorator that creates one.
    """

    normalized_before, normalized_after = _normalize_scheduling(
        "@ecs.system_plan", group, before, after
    )

    def decorate(callback: Callable[..., object]) -> SystemPlanDefinition:
        return SystemPlanDefinition(
            callback,
            name=name,
            group=group,
            before=normalized_before,
            after=normalized_after,
            parallel=bool(parallel),
        )

    if function is not None:
        return decorate(function)
    return decorate


def _normalize_scheduling(
    api_name: str,
    group: str | Iterable[str] | None,
    before: Iterable[str],
    after: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    normalized_before = tuple(str(item) for item in before)
    normalized_after = tuple(str(item) for item in after)
    if group is not None and (normalized_before or normalized_after):
        raise SystemPlanError(
            f"{api_name}(group=...) cannot also declare before=... or after=...; "
            "configure group order with gs.group() or gs.order()."
        )
    return normalized_before, normalized_after


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


__all__ = [
    "BuiltSystem",
    "PlanBuiltSystem",
    "RuntimeBuiltSystem",
    "RuntimeSystemDefinition",
    "SystemDefinition",
    "SystemPlanDefinition",
    "system",
    "system_plan",
]
