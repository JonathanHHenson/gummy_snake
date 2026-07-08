"""ECS action tree builders and execution."""

from __future__ import annotations

import builtins
import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast, get_origin, get_type_hints, overload

from gummysnake.ecs.expression_tools import ExpressionInput
from gummysnake.ecs.expressions import (
    EntityExpression,
    Expression,
    FieldExpression,
    QueryProxy,
    ensure_expr,
)
from gummysnake.ecs.specs import EventReaderProxy, EventWriterProxy, Query
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsTag
from gummysnake.exceptions import SystemExecutionError, SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


type UdfArgument = QueryProxy | Query | ExpressionInput


class Action:
    """Abstract base class for complete ECS actions."""

    def plan(self) -> SystemPlan:
        """Wrap this action tree in a system plan.

        Returns:
            A plan object that can explain or serialize the action tree.
        """

        return SystemPlan(self)


@dataclass(frozen=True)
class SystemPlan:
    """Built action plan used internally by scheduled systems and explain output."""

    action: Action

    def explain(self) -> str:
        """Describe the plan in a human-readable form.

        Returns:
            Multiline text showing the action tree that the ECS planner will execute.
        """

        from gummysnake.ecs.action_tools.explain import explain_action

        return "\n".join(explain_action(self.action))


@dataclass
class DefaultAction(Action):
    """Complete primitive or grouped action."""

    kind: str
    children: tuple[Action, ...] = ()
    target: FieldExpression | None = None
    value: Expression | None = None
    udf: RuntimeUdfDefinition | None = None
    udf_args: tuple[UdfArgument, ...] = ()
    event_writer: EventWriterProxy | None = None
    event_value: EcsEventValue | None = None
    entity_query: QueryProxy | None = None
    component_type: type[Any] | None = None
    component_value: DataclassInstance | None = None
    tag: EcsTag | None = None
    canvas_command: str | None = None
    canvas_args: tuple[Expression, ...] = ()


@dataclass
class WhenAction(Action):
    """Complete conditional chain."""

    branches: list[tuple[Expression, Action]] = field(default_factory=list)
    otherwise_action: Action | None = None

    def when(self, condition: ExpressionInput) -> _WhenBranchBuilder:
        """Add a conditional branch to this chain.

        Args:
            condition: Value or ECS expression that decides whether the branch runs.

        Returns:
            A builder used to attach actions to the branch.
        """

        return _WhenBranchBuilder(self, ensure_expr(condition))

    def otherwise(self) -> _OtherwiseBranchBuilder:
        """Add the fallback branch for this conditional chain.

        Returns:
            A builder used to attach actions that run when no ``when`` branch matches.
        """

        return _OtherwiseBranchBuilder(self)


@dataclass
class ForEachAction(Action):
    """Loop action over an ECS iterable source."""

    source: IterableSource
    body: Action
    mode: str = "sequence"


@dataclass(frozen=True, eq=False)
class LoopItem(Expression):
    name: str

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        """Return the current loop item from the expression context.

        Args:
            ctx: Current ECS expression bindings.
            world: ECS world provided by the expression evaluator.

        Returns:
            The item value bound for this ``ecs.for_each`` iteration.
        """

        del world
        return ctx[self]


@dataclass(frozen=True)
class IterableSource:
    """Marker base for Rust-serialized ECS for_each sources."""


@dataclass(frozen=True)
class UdfIterableSource(IterableSource):
    """Loop source backed by a Python UDF that returns iterable values."""

    definition: UdfIterableDefinition
    args: tuple[UdfArgument, ...]
    item: LoopItem = field(default_factory=lambda: LoopItem("item"))

    def evaluate(self, world: EcsWorld) -> Iterable[Any]:
        """Run the Python UDF and return values for ``ecs.for_each``.

        Args:
            world: ECS world used to materialize lazy UDF arguments.

        Returns:
            Iterable values produced by the UDF, or an empty tuple when it returns ``None``.
        """

        result = self.definition.call_runtime(world, self.args)
        return () if result is None else result


@dataclass(frozen=True)
class ExpressionIterableSource(IterableSource):
    """Loop source that reads iterable values from an ECS expression."""

    expression: Expression
    item: LoopItem = field(default_factory=lambda: LoopItem("item"))


@dataclass(frozen=True)
class EventIterableSource(IterableSource):
    """Loop source that visits events from an ``ecs.EventReader`` parameter."""

    reader: EventReaderProxy
    item: LoopItem = field(default_factory=lambda: LoopItem("event"))


@dataclass(frozen=True)
class EntityIteratorSource(IterableSource):
    """Loop source describing entity rows from a query iterator."""

    query: QueryProxy
    components: tuple[type[Any], ...]
    item: LoopItem = field(default_factory=lambda: LoopItem("entity"))


@dataclass(frozen=True)
class UdfDefinition:
    """Base metadata for a function decorated with ``@ecs.udf`` or ``@ecs.udf_plan``."""

    function: Callable[..., Any]
    return_annotation: object
    reads: tuple[type[Any], ...] = ()
    writes: tuple[type[Any], ...] = ()
    structural: bool = False
    side_effects: bool = False
    mutations: dict[str, frozenset[object]] = field(default_factory=dict)


@dataclass(frozen=True)
class UdfPlanDefinition(UdfDefinition):
    """Metadata for a Rust-backed expression UDF plan."""

    def __call__(self, *args: UdfArgument) -> Expression:
        """Create a logical UDF expression for a Rust-backed UDF plan."""

        coerced_args: list[Expression] = []
        for arg in args:
            if isinstance(arg, QueryProxy | Query):
                raise SystemPlanError(
                    f"Rust-backed ECS UDF {self.function.__name__} cannot take a query "
                    "parameter directly; pass field expressions instead."
                )
            coerced_args.append(ensure_expr(cast(ExpressionInput, arg)))
        result = self.function(*coerced_args)
        if result is None:
            raise SystemPlanError(
                f"Rust-backed ECS UDF {self.function.__name__} must return an ECS expression."
            )
        return ensure_expr(result)


@dataclass(frozen=True)
class _RuntimeUdfBase(UdfDefinition):
    """Shared runtime behavior for Python UDF definitions."""

    def call_runtime(self, world: EcsWorld, args: tuple[UdfArgument, ...]) -> Any:
        """Run this Python UDF with ECS arguments converted to Python values.

        Args:
            world: ECS world that owns the entities, resources, and event queues.
            args: Lazy ECS values or expressions passed to the UDF in the system plan.

        Returns:
            The value returned by the decorated Python function.
        """

        materialized = [world.materialize_udf_arg(arg) for arg in args]
        return self.function(*materialized)

    def execute_action(self, world: EcsWorld, args: tuple[UdfArgument, ...]) -> None:
        """Run this Python UDF as a side-effect action and count the call.

        Args:
            world: ECS world that owns the action runtime state.
            args: Lazy ECS values or expressions passed to the UDF in the system plan.
        """

        from gummysnake.ecs.world_runtime.python_batch import PythonEcsAccessBatch

        batch = PythonEcsAccessBatch(world)
        previous_batch = world._active_python_access_batch
        world._active_python_access_batch = batch
        try:
            self.call_runtime(world, args)
        finally:
            batch.flush()
            batch.close()
            world._active_python_access_batch = previous_batch
        world._diagnostics["ecs_udf_calls"] += 1


@dataclass(frozen=True)
class RuntimeUdfDefinition(_RuntimeUdfBase):
    """Metadata for a runtime Python UDF action."""

    def __call__(self, *args: UdfArgument) -> DefaultAction | None:
        """Create or append a Python UDF action."""

        action = DefaultAction("udf", udf=self, udf_args=tuple(args))
        if active_build_session():
            append_action(action, operation=f"@ecs.udf {self.function.__name__}()")
            return None
        return action


@dataclass(frozen=True)
class UdfIterableDefinition(_RuntimeUdfBase):
    """Metadata for a Python UDF that produces values for ``ecs.for_each``."""

    def __call__(self, *args: UdfArgument) -> UdfIterableSource:
        """Create an iterable ECS loop source from this Python UDF.

        Args:
            args: Values or ECS expressions passed to the decorated UDF.

        Returns:
            An iterable source accepted by ``ecs.for_each``.
        """

        return UdfIterableSource(self, tuple(args))


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
    """Lazy expression node for a Rust-backed ECS UDF call."""

    definition: UdfPlanDefinition
    args: tuple[UdfArgument, ...]

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        """Reject Python evaluation for Rust-backed UDF expression nodes.

        Args:
            ctx: Current ECS expression bindings.
            world: ECS world that would provide runtime storage.

        Returns:
            This method always raises because Rust-backed UDFs execute in Rust plans only.
        """

        del ctx, world
        raise SystemExecutionError(
            f"Rust-backed ECS UDF {self.definition.function.__name__!r} cannot execute in Python."
        )


@dataclass(frozen=True)
class _RuntimeUdfDecorator:
    reads: tuple[type[Any], ...] = ()
    writes: tuple[type[Any], ...] = ()
    structural: bool = False
    mutations: Mapping[str, object] | None = None

    @overload
    def __call__(self, callback: Callable[..., Iterable[Any]]) -> UdfIterableDefinition: ...

    @overload
    def __call__(self, callback: Callable[..., Any]) -> RuntimeUdfDefinition: ...

    def __call__(
        self, callback: Callable[..., Any]
    ) -> RuntimeUdfDefinition | UdfIterableDefinition:
        """Create a runtime Python UDF definition."""

        return _build_runtime_udf_definition(
            callback,
            reads=self.reads,
            writes=self.writes,
            structural=self.structural,
            mutations=self.mutations,
        )


@dataclass(frozen=True)
class _UdfPlanDecorator:
    reads: tuple[type[Any], ...] = ()
    writes: tuple[type[Any], ...] = ()
    structural: bool = False

    def __call__(self, callback: Callable[..., Any]) -> UdfPlanDefinition:
        """Create a Rust-backed UDF plan definition."""

        return _build_udf_plan_definition(
            callback,
            reads=self.reads,
            writes=self.writes,
            structural=self.structural,
        )


def _udf_type_hints(callback: Callable[..., Any]) -> dict[str, Any]:
    hints = get_type_hints(callback, include_extras=True)
    signature = inspect.signature(callback)
    for parameter in signature.parameters.values():
        if parameter.name not in hints:
            raise SystemPlanError(
                f"ECS UDF {callback.__name__} parameter {parameter.name!r} needs a type annotation."
            )
    if "return" not in hints:
        raise SystemPlanError(f"ECS UDF {callback.__name__} needs a return annotation.")
    return hints


def _build_runtime_udf_definition(
    callback: Callable[..., Any],
    *,
    reads: tuple[type[Any], ...],
    writes: tuple[type[Any], ...],
    structural: bool,
    mutations: Mapping[str, object] | None,
) -> RuntimeUdfDefinition | UdfIterableDefinition:
    hints = _udf_type_hints(callback)
    definition_type = (
        UdfIterableDefinition if _is_iterable_annotation(hints["return"]) else RuntimeUdfDefinition
    )
    return definition_type(
        callback,
        hints["return"],
        reads=reads,
        writes=writes,
        structural=structural,
        side_effects=False,
        mutations=validate_mutation_metadata(callback, mutations),
    )


def _build_udf_plan_definition(
    callback: Callable[..., Any],
    *,
    reads: tuple[type[Any], ...],
    writes: tuple[type[Any], ...],
    structural: bool,
) -> UdfPlanDefinition:
    hints = _udf_type_hints(callback)
    signature = inspect.signature(callback)
    for parameter in signature.parameters.values():
        if hints[parameter.name] is not Expression:
            raise SystemPlanError(
                f"Rust-backed ECS UDF plan {callback.__name__} parameter {parameter.name!r} "
                "must be annotated as ecs.Expression[T]. Use @ecs.udf "
                "for runtime Python vector/materialized inputs."
            )
    if hints["return"] is not Expression:
        raise SystemPlanError(
            f"Rust-backed ECS UDF plan {callback.__name__} return type must be ecs.Expression[T]."
        )
    return UdfPlanDefinition(
        callback,
        hints["return"],
        reads=reads,
        writes=writes,
        structural=structural,
        side_effects=False,
        mutations={},
    )


@overload
def udf(function: Callable[..., Iterable[Any]], /) -> UdfIterableDefinition: ...


@overload
def udf(function: Callable[..., Any], /) -> RuntimeUdfDefinition: ...


@overload
def udf(
    function: None = None,
    *,
    reads: Iterable[type[Any]] = (),
    writes: Iterable[type[Any]] = (),
    structural: bool = False,
    side_effects: bool = False,
    mutations: Mapping[str, object] | None = None,
) -> _RuntimeUdfDecorator: ...


def udf(
    function: Callable[..., Any] | None = None,
    *,
    reads: Iterable[type[Any]] = (),
    writes: Iterable[type[Any]] = (),
    structural: bool = False,
    side_effects: bool = False,
    mutations: Mapping[str, object] | None = None,
) -> _RuntimeUdfDecorator | RuntimeUdfDefinition | UdfIterableDefinition:
    """Declare a runtime Python UDF usable from ECS plans.

    Python UDFs are explicit Python execution boundaries for side effects,
    materialized entity/resource access, or iterable sources. Use
    :func:`udf_plan` for Rust-backed expression UDF plans.

    Args:
        function: Function to decorate when ``@ecs.udf`` is used without parentheses.
        reads: Component types read by a Python UDF. Reserved for compatibility metadata.
        writes: Component types written by a Python UDF. Reserved for compatibility metadata.
        structural: Whether the Python UDF may change entity structure. Reserved for
            compatibility metadata.
        side_effects: Deprecated compatibility flag. Passing ``True`` raises an error;
            use explicit ``mutations`` metadata instead.
        mutations: Entity mutation declarations keyed by Python UDF parameter name.

    Returns:
        A UDF definition, or a decorator that creates one.
    """

    if side_effects:
        raise SystemPlanError(
            "@ecs.udf(side_effects=...) has been replaced by explicit mutations={...} "
            "metadata on @ecs.udf."
        )
    decorator = _RuntimeUdfDecorator(
        reads=tuple(reads),
        writes=tuple(writes),
        structural=structural,
        mutations=mutations,
    )
    if function is not None:
        return decorator(function)
    return decorator


@overload
def udf_plan(function: Callable[..., Any], /) -> UdfPlanDefinition: ...


@overload
def udf_plan(
    function: None = None,
    *,
    reads: Iterable[type[Any]] = (),
    writes: Iterable[type[Any]] = (),
    structural: bool = False,
    side_effects: bool = False,
    mutations: Mapping[str, object] | None = None,
) -> _UdfPlanDecorator: ...


def udf_plan(
    function: Callable[..., Any] | None = None,
    *,
    reads: Iterable[type[Any]] = (),
    writes: Iterable[type[Any]] = (),
    structural: bool = False,
    side_effects: bool = False,
    mutations: Mapping[str, object] | None = None,
) -> _UdfPlanDecorator | UdfPlanDefinition:
    """Declare a Rust-backed expression UDF for ECS system plans.

    UDF plans describe pure expression work for the ECS planner and must annotate
    parameters and return values as ``ecs.Expression[T]``. Use :func:`udf` when
    the function must run Python code at ECS runtime.

    Args:
        function: Function to decorate when ``@ecs.udf_plan`` is used without parentheses.
        reads: Reserved compatibility metadata.
        writes: Reserved compatibility metadata.
        structural: Reserved compatibility metadata.
        side_effects: Deprecated compatibility flag. Passing ``True`` raises an error.
        mutations: Invalid for UDF plans; reserved for Python ``@ecs.udf`` metadata.

    Returns:
        A UDF definition, or a decorator that creates one.
    """

    if side_effects:
        raise SystemPlanError(
            "@ecs.udf_plan(side_effects=...) has been replaced by explicit mutations={...} "
            "metadata on @ecs.udf."
        )
    if mutations:
        raise SystemPlanError("@ecs.udf_plan mutations={...} metadata is only valid with @ecs.udf.")
    decorator = _UdfPlanDecorator(
        reads=tuple(reads),
        writes=tuple(writes),
        structural=structural,
    )
    if function is not None:
        return decorator(function)
    return decorator


def set(target: FieldExpression, value: ExpressionInput) -> DefaultAction:
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


def add_component_action(
    entity: EntityExpression, component: DataclassInstance | type[Any]
) -> DefaultAction:
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


def add_tag_action(entity: EntityExpression, tag: EcsTag) -> DefaultAction:
    """Build an action that adds a tag to each entity matched by a query.

    Args:
        entity: The ``query.entity`` expression that identifies which query rows to update.
        tag: Tag value to add.

    Returns:
        A structural action node for the system plan.
    """

    return DefaultAction("add_tag", entity_query=_require_entity_query(entity), tag=tag)


def remove_tag_action(entity: EntityExpression, tag: EcsTag) -> DefaultAction:
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


def emit_event(writer: EventWriterProxy, event: EcsEventValue) -> DefaultAction:
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
    "RuntimeUdfDefinition",
    "SystemPlan",
    "UdfCallExpression",
    "UdfDefinition",
    "UdfIterableDefinition",
    "UdfPlanDefinition",
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
    "udf_plan",
    "validate_mutation_metadata",
    "when",
]
