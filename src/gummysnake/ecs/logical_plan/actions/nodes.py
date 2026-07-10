"""ECS action tree builders and execution."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.logical_plan.expressions import (
    Expression,
    ExpressionInput,
    FieldExpression,
    QueryProxy,
    ensure_expr,
)
from gummysnake.ecs.logical_plan.specifications import EventReaderProxy, EventWriterProxy, Query
from gummysnake.ecs.value_types import DataclassInstance, EcsEventValue, EcsTag
from gummysnake.exceptions import SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld

    from ..building.session import _OtherwiseBranchBuilder, _WhenBranchBuilder
    from .udf import RuntimeUdfDefinition, UdfIterableDefinition


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

        from gummysnake.ecs.logical_plan.inspection.explain import explain_action

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

        from gummysnake.ecs.logical_plan.building.session import _WhenBranchBuilder

        return _WhenBranchBuilder(self, ensure_expr(condition))

    def otherwise(self) -> _OtherwiseBranchBuilder:
        """Add the fallback branch for this conditional chain.

        Returns:
            A builder used to attach actions that run when no ``when`` branch matches.
        """

        from gummysnake.ecs.logical_plan.building.session import _OtherwiseBranchBuilder

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

    mutations: dict[str, frozenset[object]] = field(default_factory=dict)

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
