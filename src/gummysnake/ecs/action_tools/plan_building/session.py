# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
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
            f"{operation} requires an active @ecs.system_plan plan-build session. "
            "Use it inside a Rust-executed @ecs.system_plan function."
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
