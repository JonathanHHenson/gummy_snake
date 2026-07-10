from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import cast

from gummysnake.ecs.action_model.plan_nodes import (
    Action,
    DefaultAction,
    EventIterableSource,
    ExpressionIterableSource,
    ForEachAction,
    IterableSource,
    LoopItem,
    WhenAction,
)
from gummysnake.ecs.action_tools.plan_building.session import (
    _BuildBlock,
    _BuildSession,
    _ConditionalContext,
    _ConditionalScope,
    _DoFactory,
    _IterableSourceWithItem,
    _parallel_action,
    _require_session,
    _sequence_action,
    active_build_session,
)
from gummysnake.ecs.expression_tools import ExpressionInput
from gummysnake.ecs.expressions import Expression, ensure_expr
from gummysnake.ecs.specs import EventReader, EventReaderProxy
from gummysnake.exceptions import SystemPlanError


type ForEachSource = IterableSource | EventReaderProxy | EventReader | Expression


class _BranchContext:
    def __init__(
        self,
        condition: Expression | None,
        *,
        parallel: bool | None = None,
        otherwise: bool = False,
    ) -> None:
        self.condition = condition
        self.parallel = parallel
        self.otherwise = otherwise
        self.block: _BuildBlock | None = None
        self._session: _BuildSession | None = None
        self._scope: _ConditionalScope | None = None

    def __enter__(self) -> None:
        session = _require_session("ecs.when()/ecs.otherwise()")
        scope = session.current_conditional
        if scope is None:
            raise SystemPlanError(
                "ecs.when() and ecs.otherwise() can only be used inside with ecs.conditional()."
            )
        if scope.active_branch:
            raise SystemPlanError(
                "ECS conditional branches cannot be nested without closing the first branch."
            )
        if self.otherwise and scope.otherwise_action is not None:
            raise SystemPlanError("An ECS conditional can only have one otherwise branch.")
        if self.otherwise and self.condition is not None:
            raise SystemPlanError("ecs.otherwise() cannot have a condition.")
        if not self.otherwise and scope.otherwise_action is not None:
            raise SystemPlanError("ecs.when() branches must appear before ecs.otherwise().")
        self._session = session
        self._scope = scope
        self.block = _BuildBlock(scope.branch_mode(self.parallel))
        scope.active_branch = True
        session.push_block(self.block)
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc, traceback
        if self._session is None or self._scope is None or self.block is None:
            raise SystemPlanError("ECS conditional branch was exited before it was entered.")
        self._session.pop_block(self.block)
        self._scope.active_branch = False
        if exc_type is None:
            action = self.block.to_action()
            if self.otherwise:
                self._scope.otherwise_action = action
            else:
                assert self.condition is not None
                self._scope.branches.append((self.condition, action))
        self._session = None
        self._scope = None
        self.block = None


class _ForEachContext:
    def __init__(
        self,
        source: IterableSource,
        *,
        loop_parallel: bool = False,
        block_parallel: bool = False,
    ) -> None:
        self.source = source
        self.loop_parallel = loop_parallel
        self.block_parallel = block_parallel
        self.block = _BuildBlock("parallel" if block_parallel else "sequence")
        self._session: _BuildSession | None = None

    @property
    def item(self) -> LoopItem:
        return cast(_IterableSourceWithItem, self.source).item

    def __enter__(self) -> LoopItem:
        self._session = _require_session("with ecs.for_each")
        self._session.push_block(self.block)
        return self.item

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc, traceback
        if self._session is None:
            raise SystemPlanError("ECS for_each block was exited before it was entered.")
        self._session.pop_block(self.block)
        if exc_type is None:
            mode = "parallel" if self.loop_parallel else "sequence"
            self._session.append(ForEachAction(self.source, self.block.to_action(), mode=mode))
        self._session = None

    def do(self, *actions: Action) -> ForEachAction:
        return ForEachAction(self.source, _sequence_action(*actions), mode="sequence")

    def do_in_order(self, *actions: Action) -> ForEachAction:
        return self.do(*actions)

    def do_in_parallel(self, *actions: Action) -> ForEachAction:
        return ForEachAction(self.source, _parallel_action(*actions), mode="parallel")


@dataclass
class _WhenBranchBuilder:
    chain: WhenAction | None
    condition: Expression

    def do(self, *actions: Action) -> WhenAction:
        action = _sequence_action(*actions)
        chain = self.chain or WhenAction()
        chain.branches.append((self.condition, action))
        return chain

    def do_in_order(self, *actions: Action) -> WhenAction:
        return self.do(do_in_order(*actions))

    def do_in_parallel(self, *actions: Action) -> WhenAction:
        return self.do(do_in_parallel(*actions))


@dataclass
class _OtherwiseBranchBuilder:
    chain: WhenAction

    def do(self, *actions: Action) -> WhenAction:
        if self.chain.otherwise_action is not None:
            raise SystemPlanError("A conditional chain can only have one otherwise() branch.")
        self.chain.otherwise_action = _sequence_action(*actions)
        return self.chain

    def do_in_order(self, *actions: Action) -> WhenAction:
        return self.do(do_in_order(*actions))

    def do_in_parallel(self, *actions: Action) -> WhenAction:
        return self.do(do_in_parallel(*actions))


def _validate_actions(actions: tuple[Action, ...]) -> None:
    for action in actions:
        if not isinstance(action, Action):
            raise SystemPlanError(f"Expected ECS Action, got {type(action).__name__}.")


def _group_action(kind: str, *actions: Action) -> DefaultAction:
    _validate_actions(actions)
    return DefaultAction(kind, children=tuple(actions)) if actions else DefaultAction("noop")


def _sequence_action(*actions: Action) -> DefaultAction:
    return _group_action("sequence", *actions)


def _parallel_action(*actions: Action) -> DefaultAction:
    return _group_action("parallel", *actions)


do = _DoFactory()


def do_in_order(*actions: Action) -> DefaultAction:
    """Return a sequence action that runs child actions in order."""

    return _sequence_action(*actions)


def do_in_parallel(*actions: Action) -> DefaultAction:
    """Return a parallel action for independent child actions."""

    return _parallel_action(*actions)


def conditional(*, parallel: bool = False) -> _ConditionalContext:
    """Return a context manager that records an ``ecs.when`` / ``ecs.otherwise`` chain."""

    return _ConditionalContext(parallel=parallel)


def when(condition: ExpressionInput, *, parallel: bool | None = None) -> _BranchContext:
    """Return a builder or context manager for a conditional ECS branch.

    Args:
        condition: Value or ECS expression that decides whether the branch runs.
        parallel: Override whether actions inside this branch may run in parallel.

    Returns:
        A context manager inside ``with ecs.conditional()`` blocks, or a branch builder for
        the older direct action-building style.
    """

    expr = ensure_expr(condition)
    if active_build_session():
        return _BranchContext(expr, parallel=parallel)
    return cast(_BranchContext, _WhenBranchBuilder(None, expr))


def otherwise(*, parallel: bool | None = None) -> _BranchContext:
    """Return a context manager for the fallback branch of an ECS conditional.

    Args:
        parallel: Override whether actions inside the fallback branch may run in parallel.

    Returns:
        A context manager used inside ``with ecs.conditional()`` blocks.
    """

    return _BranchContext(None, parallel=parallel, otherwise=True)


def _iterable_source_for(source: ForEachSource) -> IterableSource:
    if isinstance(source, IterableSource):
        return source
    if isinstance(source, EventReaderProxy):
        return EventIterableSource(source)
    if isinstance(source, Expression):
        return ExpressionIterableSource(source)
    raise SystemPlanError(
        "ecs.for_each() accepts EventReader parameters, annotated @ecs.udf iterable sources, "
        "or list/vector field expressions. Python iterables would execute during plan build."
    )


def for_each(
    source: ForEachSource, *, loop_parallel: bool = False, block_parallel: bool = False
) -> _ForEachContext:
    """Return a context manager that records a loop over an ECS iterable source.

    Args:
        source: Event reader, iterable UDF source, or iterable ECS expression to loop over.
        loop_parallel: Whether each loop item may be processed independently in parallel.
        block_parallel: Whether actions recorded inside one loop item may run in parallel.

    Returns:
        A context manager whose ``item`` is the current loop value expression.
    """

    return _ForEachContext(
        _iterable_source_for(source),
        loop_parallel=loop_parallel,
        block_parallel=block_parallel,
    )
