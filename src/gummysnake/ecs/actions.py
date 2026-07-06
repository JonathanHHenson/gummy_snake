"""ECS action tree builders and execution."""

from __future__ import annotations

import builtins
import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, get_origin, get_type_hints, overload

from gummysnake.ecs.expressions import (
    EntityExpression,
    Expression,
    FieldExpression,
    QueryProxy,
    ensure_expr,
)
from gummysnake.ecs.specs import EventReaderProxy, EventWriterProxy
from gummysnake.exceptions import SystemExecutionError, SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


class Action:
    """Abstract base class for complete ECS actions."""

    def plan(self) -> SystemPlan:
        return SystemPlan(self)


@dataclass(frozen=True)
class SystemPlan:
    """Built action plan used internally by scheduled systems and explain output."""

    action: Action

    def explain(self) -> str:
        from gummysnake.ecs.action_tools.explain import explain_action

        return "\n".join(explain_action(self.action))


@dataclass
class DefaultAction(Action):
    """Complete primitive or grouped action."""

    kind: str
    children: tuple[Action, ...] = ()
    target: FieldExpression | None = None
    value: Expression | None = None
    udf: UdfDefinition | None = None
    udf_args: tuple[object, ...] = ()
    event_writer: EventWriterProxy | None = None
    event_value: object | None = None
    entity_query: QueryProxy | None = None
    component_type: type[Any] | None = None
    component_value: object | None = None
    tag: object | None = None


@dataclass
class WhenAction(Action):
    """Complete conditional chain."""

    branches: list[tuple[Expression, Action]] = field(default_factory=list)
    otherwise_action: Action | None = None

    def when(self, condition: object) -> _WhenBranchBuilder:
        return _WhenBranchBuilder(self, ensure_expr(condition))

    def otherwise(self) -> _OtherwiseBranchBuilder:
        return _OtherwiseBranchBuilder(self)


@dataclass
class ForEachAction(Action):
    source: IterableSource
    body: Action
    mode: str = "sequence"


@dataclass(frozen=True, eq=False)
class LoopItem(Expression):
    name: str

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        del world
        return ctx[self]


@dataclass(frozen=True)
class IterableSource:
    """Marker base for Rust-serialized ECS for_each sources."""


@dataclass(frozen=True)
class UdfIterableSource(IterableSource):
    definition: UdfDefinition
    args: tuple[object, ...]
    item: LoopItem = field(default_factory=lambda: LoopItem("item"))

    def evaluate(self, world: EcsWorld) -> Iterable[Any]:
        result = self.definition.call_runtime(world, self.args)
        return () if result is None else result


@dataclass(frozen=True)
class ExpressionIterableSource(IterableSource):
    expression: Expression
    item: LoopItem = field(default_factory=lambda: LoopItem("item"))


@dataclass(frozen=True)
class EventIterableSource(IterableSource):
    reader: EventReaderProxy
    item: LoopItem = field(default_factory=lambda: LoopItem("event"))


@dataclass(frozen=True)
class EntityIteratorSource(IterableSource):
    query: QueryProxy
    components: tuple[type[Any], ...]
    item: LoopItem = field(default_factory=lambda: LoopItem("entity"))


@dataclass(frozen=True)
class UdfDefinition:
    function: Callable[..., Any]
    return_annotation: object
    reads: tuple[type[Any], ...] = ()
    writes: tuple[type[Any], ...] = ()
    structural: bool = False
    side_effects: bool = False
    python: bool = False
    mutations: dict[str, frozenset[object]] = field(default_factory=dict)

    def __call__(self, *args: object) -> DefaultAction | UdfIterableSource | UdfCallExpression:
        if not self.python:
            return UdfCallExpression(self, tuple(args))
        if _is_iterable_annotation(self.return_annotation):
            return UdfIterableSource(self, tuple(args))
        action = DefaultAction("udf", udf=self, udf_args=tuple(args))
        if active_build_session():
            append_action(action, operation=f"@ecs.udf(python=True) {self.function.__name__}()")
            return None  # type: ignore[return-value]
        return action

    def call_runtime(self, world: EcsWorld, args: tuple[object, ...]) -> Any:
        materialized = [world.materialize_udf_arg(arg) for arg in args]
        return self.function(*materialized)

    def execute_action(self, world: EcsWorld, args: tuple[object, ...]) -> None:
        self.call_runtime(world, args)
        world._diagnostics["ecs_udf_calls"] += 1


def validate_mutation_metadata(
    callback: Callable[..., Any], mutations: Mapping[str, object] | None
) -> dict[str, frozenset[object]]:
    """Validate EntityMutation metadata keyed by callback parameter name."""

    if not mutations:
        return {}
    from gummysnake.ecs.world import EntityMutation

    parameter_names = builtins.set(inspect.signature(callback).parameters)
    normalized: dict[str, frozenset[object]] = {}
    for parameter_name, declared in mutations.items():
        if parameter_name not in parameter_names:
            raise SystemPlanError(
                f"ECS mutation metadata for {callback.__name__} references unknown "
                f"parameter {parameter_name!r}."
            )
        if isinstance(declared, EntityMutation):
            mutation_set = frozenset({declared})
        elif isinstance(declared, Iterable) and not isinstance(declared, str | bytes):
            mutation_set = frozenset(declared)
        else:
            raise SystemPlanError(
                f"ECS mutation metadata for {parameter_name!r} must be a set of "
                "ecs.EntityMutation[...] declarations."
            )
        if not mutation_set:
            raise SystemPlanError(f"ECS mutation metadata for {parameter_name!r} cannot be empty.")
        for mutation in mutation_set:
            if not isinstance(mutation, EntityMutation):
                raise SystemPlanError(
                    f"ECS mutation metadata for {parameter_name!r} must contain only "
                    "ecs.EntityMutation[...] declarations."
                )
        normalized[parameter_name] = mutation_set
    return normalized


def _is_iterable_annotation(annotation: object) -> bool:
    origin = get_origin(annotation)
    if origin is None:
        return False
    return origin in {Iterable, list, tuple} or getattr(origin, "__name__", "") in {
        "Iterable",
        "Iterator",
        "Generator",
    }


@dataclass(frozen=True, eq=False)
class UdfCallExpression(Expression):
    definition: UdfDefinition
    args: tuple[object, ...]

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        del ctx, world
        raise SystemExecutionError(
            f"Rust-backed ECS UDF {self.definition.function.__name__!r} cannot execute in Python."
        )


@overload
def udf(function: Callable[..., Any], /) -> UdfDefinition: ...


@overload
def udf(
    function: None = None,
    *,
    reads: Iterable[type[Any]] = (),
    writes: Iterable[type[Any]] = (),
    structural: bool = False,
    side_effects: bool = False,
    python: bool = False,
    mutations: dict[str, object] | None = None,
) -> Callable[[Callable[..., Any]], UdfDefinition]: ...


def udf(
    function: Callable[..., Any] | None = None,
    *,
    reads: Iterable[type[Any]] = (),
    writes: Iterable[type[Any]] = (),
    structural: bool = False,
    side_effects: bool = False,
    python: bool = False,
    mutations: dict[str, object] | None = None,
) -> Callable[[Callable[..., Any]], UdfDefinition] | UdfDefinition:
    if side_effects:
        raise SystemPlanError(
            "@ecs.udf(side_effects=...) has been replaced by explicit mutations={...} metadata "
            "on @ecs.udf(python=True)."
        )

    def decorate(callback: Callable[..., Any]) -> UdfDefinition:
        if mutations and not python:
            raise SystemPlanError(
                "@ecs.udf mutations={...} metadata is only valid with @ecs.udf(python=True)."
            )
        normalized_mutations = validate_mutation_metadata(callback, mutations)
        hints = get_type_hints(callback, include_extras=True)
        signature = inspect.signature(callback)
        for parameter in signature.parameters.values():
            if parameter.name not in hints:
                raise SystemPlanError(
                    f"ECS UDF {callback.__name__} parameter {parameter.name!r} needs a "
                    "type annotation."
                )
            if not python and hints[parameter.name] is not Expression:
                raise SystemPlanError(
                    f"Rust-backed ECS UDF {callback.__name__} parameter {parameter.name!r} "
                    "must be annotated as ecs.Expression[T]. Use @ecs.udf(python=True) "
                    "for runtime Python vector/materialized inputs."
                )
        if "return" not in hints:
            raise SystemPlanError(f"ECS UDF {callback.__name__} needs a return annotation.")
        if not python and hints["return"] is not Expression:
            raise SystemPlanError(
                f"Rust-backed ECS UDF {callback.__name__} return type must be ecs.Expression[T]."
            )
        return UdfDefinition(
            callback,
            hints["return"],
            reads=tuple(reads),
            writes=tuple(writes),
            structural=structural,
            side_effects=False,
            python=python,
            mutations=normalized_mutations,
        )

    if function is not None:
        return decorate(function)
    return decorate


def set(target: FieldExpression, value: object) -> DefaultAction:
    """Build an ECS action that assigns a value to a component or resource field.

    Args:
        target: Writable field expression, such as ``query.position.x`` or a resource field.
        value: Python value or ECS expression to store in the target field.

    Returns:
        A complete action node that can be added to a system plan.
    """

    if not isinstance(target, FieldExpression):
        raise SystemPlanError("ecs.set() target must be a component or resource field expression.")
    return DefaultAction("set", target=target, value=ensure_expr(value))


def add_component_action(entity: EntityExpression, component: object | type[Any]) -> DefaultAction:
    """Build an action that adds a component to each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to update.
        component: Component type to add, or a component instance whose field values should be used.

    Returns:
        A structural action node for the system plan.
    """

    component_type = component if isinstance(component, type) else type(component)
    return DefaultAction(
        "add_component",
        entity_query=_require_entity_query(entity),
        component_type=component_type,
        component_value=None if isinstance(component, type) else component,
    )


def remove_component_action(entity: EntityExpression, component_type: type[Any]) -> DefaultAction:
    """Build an action that removes a component from each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to update.
        component_type: Component class to remove from each matched entity.

    Returns:
        A structural action node for the system plan.
    """

    return DefaultAction(
        "remove_component",
        entity_query=_require_entity_query(entity),
        component_type=component_type,
    )


def add_tag_action(entity: EntityExpression, tag: object) -> DefaultAction:
    """Build an action that adds a tag to each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to update.
        tag: Tag value to add.

    Returns:
        A structural action node for the system plan.
    """

    return DefaultAction("add_tag", entity_query=_require_entity_query(entity), tag=tag)


def remove_tag_action(entity: EntityExpression, tag: object) -> DefaultAction:
    """Build an action that removes a tag from each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to update.
        tag: Tag value to remove.

    Returns:
        A structural action node for the system plan.
    """

    return DefaultAction("remove_tag", entity_query=_require_entity_query(entity), tag=tag)


def despawn_action(entity: EntityExpression) -> DefaultAction:
    """Build an action that despawns each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to despawn.

    Returns:
        A structural action node for the system plan.
    """

    return DefaultAction("despawn", entity_query=_require_entity_query(entity))


def _require_entity_query(entity: EntityExpression) -> QueryProxy:
    if not isinstance(entity, EntityExpression):
        raise SystemPlanError(
            "ECS structural actions require query.entity from an ecs.Query parameter."
        )
    return entity.query


def emit_event(writer: EventWriterProxy, event: object) -> DefaultAction:
    """Build an action that sends an ECS event.

    Args:
        writer: Event writer proxy received by a system function.
        event: Event dataclass instance to enqueue.

    Returns:
        An event-emission action node for the system plan.
    """

    if not isinstance(writer, EventWriterProxy):
        raise SystemPlanError("ecs.emit_event() expects an ecs.EventWriter[...] parameter.")
    return DefaultAction("emit_event", event_writer=writer, event_value=event)


from gummysnake.ecs.action_tools.building import (  # noqa: E402
    _OtherwiseBranchBuilder,
    _WhenBranchBuilder,
    active_build_session,
    append_action,
    build_session,
    conditional,
    do,
    do_in_order,
    do_in_parallel,
    for_each,
    otherwise,
    when,
)


def action_write_targets(action: Action) -> builtins.set[tuple[object, type[Any], str]]:
    """Return field or structural targets written by an action tree.

    Args:
        action: Root action node to inspect.

    Returns:
        A set of ``(source, component_type, field_name)`` tuples used for conflict checks.
    """

    from gummysnake.ecs.action_tools.analysis import action_write_targets as analyze

    return analyze(action)


def action_query_refs(action: Action) -> builtins.set[QueryProxy]:
    """Return query proxies referenced by an action tree.

    Args:
        action: Root action node to inspect.

    Returns:
        Query proxies used by the action or any nested child action.
    """

    from gummysnake.ecs.action_tools.analysis import action_query_refs as analyze

    return analyze(action)


__all__ = [
    "Action",
    "DefaultAction",
    "EntityIteratorSource",
    "EventIterableSource",
    "ExpressionIterableSource",
    "ForEachAction",
    "IterableSource",
    "SystemPlan",
    "UdfCallExpression",
    "UdfDefinition",
    "WhenAction",
    "active_build_session",
    "add_component_action",
    "add_tag_action",
    "append_action",
    "build_session",
    "conditional",
    "despawn_action",
    "do",
    "do_in_order",
    "do_in_parallel",
    "emit_event",
    "for_each",
    "otherwise",
    "remove_component_action",
    "remove_tag_action",
    "set",
    "udf",
    "validate_mutation_metadata",
    "when",
]
