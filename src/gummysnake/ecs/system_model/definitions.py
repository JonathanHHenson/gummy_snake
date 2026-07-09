# pyright: reportNoOverloadImplementation=false
# pyright: reportInconsistentOverload=false
# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
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
