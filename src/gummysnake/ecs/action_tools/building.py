"""Context-manager helpers for building ECS action plans."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from types import TracebackType
from typing import Protocol, cast, overload

from gummysnake.ecs.actions import (
    Action,
    DefaultAction,
    EventIterableSource,
    ExpressionIterableSource,
    ForEachAction,
    IterableSource,
    LoopItem,
    WhenAction,
)
from gummysnake.ecs.expression_tools import ExpressionInput
from gummysnake.ecs.expressions import Expression, ensure_expr
from gummysnake.ecs.specs import EventReader, EventReaderProxy
from gummysnake.exceptions import SystemPlanError

type ForEachSource = IterableSource | EventReaderProxy | EventReader | Expression


class _IterableSourceWithItem(Protocol):
    item: LoopItem


@dataclass
class _BuildBlock:
    mode: str = "sequence"
    children: list[Action] = field(default_factory=list)

    def append(self, action: Action) -> None:
        if not isinstance(action, Action):
            raise SystemPlanError(f"Expected ECS Action, got {type(action).__name__}.")
        self.children.append(action)

    def to_action(self) -> Action:
        if self.mode == "parallel":
            return _parallel_action(*self.children)
        return _sequence_action(*self.children)


@dataclass
class _ConditionalScope:
    parallel: bool = False
    branches: list[tuple[Expression, Action]] = field(default_factory=list)
    otherwise_action: Action | None = None
    active_branch: bool = False

    def branch_mode(self, override: bool | None) -> str:
        return "parallel" if (self.parallel if override is None else override) else "sequence"

    def to_action(self) -> WhenAction:
        return WhenAction(list(self.branches), self.otherwise_action)


class _BuildSession:
    def __init__(self, *, parallel: bool = False) -> None:
        self.root = _BuildBlock("parallel" if parallel else "sequence")
        self.blocks: list[_BuildBlock] = [self.root]
        self.conditionals: list[_ConditionalScope] = []

    @property
    def current_block(self) -> _BuildBlock:
        return self.blocks[-1]

    @property
    def current_conditional(self) -> _ConditionalScope | None:
        return self.conditionals[-1] if self.conditionals else None

    def append(self, action: Action) -> None:
        self.current_block.append(action)

    def push_block(self, block: _BuildBlock) -> None:
        self.blocks.append(block)

    def pop_block(self, block: _BuildBlock) -> None:
        if not self.blocks or self.blocks[-1] is not block:
            raise SystemPlanError("ECS plan-build block stack became unbalanced.")
        self.blocks.pop()

    def push_conditional(self, conditional: _ConditionalScope) -> None:
        self.conditionals.append(conditional)

    def pop_conditional(self, conditional: _ConditionalScope) -> None:
        if not self.conditionals or self.conditionals[-1] is not conditional:
            raise SystemPlanError("ECS conditional plan-build stack became unbalanced.")
        self.conditionals.pop()

    def finish(self) -> Action:
        if len(self.blocks) != 1:
            raise SystemPlanError("ECS system plan has unclosed with ecs.do/when/for_each blocks.")
        if self.conditionals:
            raise SystemPlanError("ECS system plan has an unclosed ecs.conditional() block.")
        return self.root.to_action()


_BUILD_STACK: contextvars.ContextVar[tuple[_BuildSession, ...]] = contextvars.ContextVar(
    "gummysnake_ecs_build_stack", default=()
)


def _current_session() -> _BuildSession | None:
    stack = _BUILD_STACK.get()
    return stack[-1] if stack else None


def _require_session(operation: str) -> _BuildSession:
    session = _current_session()
    if session is None:
        raise SystemPlanError(
            f"{operation} requires an active @ecs.system plan-build session. "
            "Use it inside a Rust-executed @ecs.system function."
        )
    return session


def active_build_session() -> bool:
    """Return whether code is currently building an ECS logical plan."""

    return _current_session() is not None


def append_action(action: Action, *, operation: str = "ECS plan mutation") -> None:
    """Append an action to the active context-manager build block."""

    _require_session(operation).append(action)


class _BuildSessionContext:
    def __init__(self, *, parallel: bool = False) -> None:
        self.session = _BuildSession(parallel=parallel)
        self._token: contextvars.Token[tuple[_BuildSession, ...]] | None = None

    def __enter__(self) -> _BuildSession:
        stack = _BUILD_STACK.get()
        self._token = _BUILD_STACK.set((*stack, self.session))
        return self.session

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        if self._token is None:
            raise SystemPlanError("ECS plan-build session was exited before it was entered.")
        stack = _BUILD_STACK.get()
        if not stack or stack[-1] is not self.session:
            _BUILD_STACK.reset(self._token)
            raise SystemPlanError("ECS plan-build session stack became unbalanced.")
        _BUILD_STACK.reset(self._token)
        self._token = None


def build_session(*, parallel: bool = False) -> _BuildSessionContext:
    """Create a context manager for recording ECS actions during system registration.

    Args:
        parallel: When true, sibling actions recorded in the root block may run in parallel.

    Returns:
        A context manager that owns the temporary plan-build session.
    """

    return _BuildSessionContext(parallel=parallel)


class _BlockContext:
    def __init__(self, *, parallel: bool = False) -> None:
        self.block = _BuildBlock("parallel" if parallel else "sequence")
        self._session: _BuildSession | None = None

    def __enter__(self) -> None:
        self._session = _require_session("with ecs.do")
        self._session.push_block(self.block)
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc, traceback
        if self._session is None:
            raise SystemPlanError("ECS do block was exited before it was entered.")
        self._session.pop_block(self.block)
        if exc_type is None:
            self._session.append(self.block.to_action())
        self._session = None


class _DoFactory:
    """Factory and context manager behind the public ``ecs.do`` helper."""

    def __init__(self) -> None:
        self._entered: list[_BlockContext] = []

    @overload
    def __call__(self, *, parallel: bool = False) -> _BlockContext: ...

    @overload
    def __call__(self, action: Action, /, *actions: Action, parallel: bool = False) -> Action: ...

    def __call__(self, *actions: Action, parallel: bool = False) -> Action | _BlockContext:
        """Create a grouped action or open a plan-build block."""

        if actions:
            return _parallel_action(*actions) if parallel else _sequence_action(*actions)
        return _BlockContext(parallel=parallel)

    def __enter__(self) -> None:
        context = _BlockContext(parallel=False)
        self._entered.append(context)
        return context.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._entered:
            raise SystemPlanError("ecs.do context manager was exited before it was entered.")
        context = self._entered.pop()
        return context.__exit__(exc_type, exc, traceback)


class _ConditionalContext:
    def __init__(self, *, parallel: bool = False) -> None:
        self.scope = _ConditionalScope(parallel=parallel)
        self._session: _BuildSession | None = None

    def __enter__(self) -> None:
        self._session = _require_session("with ecs.conditional")
        self._session.push_conditional(self.scope)
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc, traceback
        if self._session is None:
            raise SystemPlanError("ECS conditional block was exited before it was entered.")
        if self.scope.active_branch:
            raise SystemPlanError("ECS conditional branch stack became unbalanced.")
        self._session.pop_conditional(self.scope)
        if exc_type is None:
            self._session.append(self.scope.to_action())
        self._session = None


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
