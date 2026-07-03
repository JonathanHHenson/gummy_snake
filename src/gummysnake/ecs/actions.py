"""ECS action tree builders and execution."""

from __future__ import annotations

import builtins
import contextvars
import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Any, cast, get_origin, get_type_hints, overload

from gummysnake.ecs.expressions import (
    AttributeExpression,
    BinaryExpression,
    DeltatimeExpression,
    EntityExpression,
    ExistsExpression,
    Expression,
    FieldExpression,
    FunctionExpression,
    GroupedAnyExpression,
    GroupedValueAggregateExpression,
    KeyDownExpression,
    LiteralExpression,
    QueryProxy,
    ResourceProxy,
    UnaryExpression,
    ensure_expr,
    expression_queries,
)
from gummysnake.ecs.specs import EventReaderProxy, EventWriterProxy
from gummysnake.exceptions import SystemExecutionError, SystemPlanError

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


class Action:
    """Abstract base class for complete ECS actions."""

    def plan(self) -> SystemPlan:
        return SystemPlan(self)

    def execute(self, world: EcsWorld, contexts: list[dict[object, Any]]) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class SystemPlan:
    """Built action plan used internally by scheduled systems and explain output."""

    action: Action

    def explain(self) -> str:
        return "\n".join(_explain_action(self.action))


@dataclass
class DefaultAction(Action):
    """Complete primitive or grouped action."""

    kind: str
    children: tuple[Action, ...] = ()
    target: FieldExpression | None = None
    value: Expression | None = None
    source: object | None = None
    udf: UdfDefinition | None = None
    udf_args: tuple[object, ...] = ()
    event_writer: EventWriterProxy | None = None
    event_value: object | None = None
    entity_query: QueryProxy | None = None
    component_type: type[Any] | None = None
    component_value: object | None = None
    tag: object | None = None

    def execute(self, world: EcsWorld, contexts: list[dict[object, Any]]) -> None:
        del contexts
        if self.kind == "udf":
            if self.udf is None:
                raise SystemExecutionError("Malformed ECS UDF action.")
            self.udf.execute_action(world, self.udf_args)
            return
        raise SystemExecutionError(
            "Non-UDF ECS actions must execute through the Rust physical executor; "
            f"Python execution for action kind {self.kind!r} is disabled."
        )


@dataclass
class WhenAction(Action):
    """Complete conditional chain."""

    branches: list[tuple[Expression, Action]] = field(default_factory=list)
    otherwise_action: Action | None = None

    def when(self, condition: object) -> _WhenBranchBuilder:
        return _WhenBranchBuilder(self, ensure_expr(condition))

    def otherwise(self) -> _OtherwiseBranchBuilder:
        return _OtherwiseBranchBuilder(self)

    def execute(self, world: EcsWorld, contexts: list[dict[object, Any]]) -> None:
        del world, contexts
        raise SystemExecutionError(
            "Conditional ECS actions must execute through the Rust physical executor; "
            "Python execution is disabled."
        )


@dataclass
class ForEachAction(Action):
    source: IterableSource
    body: Action
    mode: str = "sequence"

    def execute(self, world: EcsWorld, contexts: list[dict[object, Any]]) -> None:
        del world, contexts
        raise SystemExecutionError(
            "for_each ECS actions must execute through the Rust physical executor; "
            "Python execution is disabled."
        )


@dataclass(frozen=True, eq=False)
class LoopItem(Expression):
    name: str

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        del world
        return ctx[self]


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
    def __init__(self) -> None:
        self._entered: list[_BlockContext] = []

    @overload
    def __call__(self, *, parallel: bool = False) -> _BlockContext: ...

    @overload
    def __call__(self, action: Action, /, *actions: Action, parallel: bool = False) -> Action: ...

    def __call__(self, *actions: Action, parallel: bool = False) -> Action | _BlockContext:
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
                "ecs.when() and ecs.otherwise() can only be used inside with ecs.conditional():."
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
        return cast(Any, self.source).item

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


@dataclass
class _ForEachBuilder:
    source: IterableSource

    @property
    def item(self) -> LoopItem:
        return cast(Any, self.source).item

    def do(self, *actions: Action) -> ForEachAction:
        return ForEachAction(self.source, _sequence_action(*actions), mode="sequence")

    def do_in_order(self, *actions: Action) -> ForEachAction:
        return ForEachAction(self.source, do_in_order(*actions), mode="sequence")

    def do_in_parallel(self, *actions: Action) -> ForEachAction:
        return ForEachAction(self.source, do_in_parallel(*actions), mode="parallel")


@dataclass(frozen=True)
class IterableSource:
    def iter_items(
        self, world: EcsWorld, contexts: list[dict[object, Any]]
    ) -> Iterable[tuple[dict[object, Any], Any]]:
        raise NotImplementedError


@dataclass(frozen=True)
class UdfIterableSource(IterableSource):
    definition: UdfDefinition
    args: tuple[object, ...]
    item: LoopItem = field(default_factory=lambda: LoopItem("item"))

    def evaluate(self, world: EcsWorld) -> Iterable[Any]:
        result = self.definition.call_runtime(world, self.args)
        if result is None:
            return ()
        return result

    def iter_items(
        self, world: EcsWorld, contexts: list[dict[object, Any]]
    ) -> Iterable[tuple[dict[object, Any], Any]]:
        del contexts
        for item in self.evaluate(world):
            yield {}, item


@dataclass(frozen=True)
class ExpressionIterableSource(IterableSource):
    expression: Expression
    item: LoopItem = field(default_factory=lambda: LoopItem("item"))

    def iter_items(
        self, world: EcsWorld, contexts: list[dict[object, Any]]
    ) -> Iterable[tuple[dict[object, Any], Any]]:
        queries = expression_queries(self.expression)
        for base_ctx in contexts:
            for ctx in world.iter_join_contexts_for_queries(base_ctx, queries):
                value = self.expression.eval(ctx, world)
                if value is None:
                    continue
                for item in value:
                    yield ctx, item


@dataclass(frozen=True)
class EventIterableSource(IterableSource):
    reader: EventReaderProxy
    item: LoopItem = field(default_factory=lambda: LoopItem("event"))

    def iter_items(
        self, world: EcsWorld, contexts: list[dict[object, Any]]
    ) -> Iterable[tuple[dict[object, Any], Any]]:
        del contexts
        for event in world.read_events(self.reader.event_type):
            yield {}, event


@dataclass(frozen=True)
class EntityIteratorSource(IterableSource):
    query: QueryProxy
    components: tuple[type[Any], ...]
    item: LoopItem = field(default_factory=lambda: LoopItem("entity"))

    def iter_items(
        self, world: EcsWorld, contexts: list[dict[object, Any]]
    ) -> Iterable[tuple[dict[object, Any], Any]]:
        del contexts
        from gummysnake.ecs.specs import QuerySpec

        for entity in world.match_query(cast(QuerySpec, self.query.spec)):
            yield {}, entity


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
    if not isinstance(target, FieldExpression):
        raise SystemPlanError("ecs.set() target must be a component or resource field expression.")
    return DefaultAction("set", target=target, value=ensure_expr(value))


def add_component_action(entity: EntityExpression, component: object | type[Any]) -> DefaultAction:
    if not isinstance(entity, EntityExpression):
        raise SystemPlanError(
            "ECS structural actions require query.entity from an ecs.Query parameter."
        )
    component_type = component if isinstance(component, type) else type(component)
    return DefaultAction(
        "add_component",
        entity_query=entity.query,
        component_type=component_type,
        component_value=None if isinstance(component, type) else component,
    )


def remove_component_action(entity: EntityExpression, component_type: type[Any]) -> DefaultAction:
    if not isinstance(entity, EntityExpression):
        raise SystemPlanError(
            "ECS structural actions require query.entity from an ecs.Query parameter."
        )
    return DefaultAction(
        "remove_component", entity_query=entity.query, component_type=component_type
    )


def add_tag_action(entity: EntityExpression, tag: object) -> DefaultAction:
    if not isinstance(entity, EntityExpression):
        raise SystemPlanError(
            "ECS structural actions require query.entity from an ecs.Query parameter."
        )
    return DefaultAction("add_tag", entity_query=entity.query, tag=tag)


def remove_tag_action(entity: EntityExpression, tag: object) -> DefaultAction:
    if not isinstance(entity, EntityExpression):
        raise SystemPlanError(
            "ECS structural actions require query.entity from an ecs.Query parameter."
        )
    return DefaultAction("remove_tag", entity_query=entity.query, tag=tag)


def despawn_action(entity: EntityExpression) -> DefaultAction:
    if not isinstance(entity, EntityExpression):
        raise SystemPlanError(
            "ECS structural actions require query.entity from an ecs.Query parameter."
        )
    return DefaultAction("despawn", entity_query=entity.query)


def _sequence_action(*actions: Action) -> DefaultAction:
    if not actions:
        return DefaultAction("noop")
    _validate_actions(actions)
    return DefaultAction("sequence", children=tuple(actions))


def _parallel_action(*actions: Action) -> DefaultAction:
    _validate_actions(actions)
    if not actions:
        return DefaultAction("noop")
    return DefaultAction("parallel", children=tuple(actions))


do = _DoFactory()


def do_in_order(*actions: Action) -> DefaultAction:
    return _sequence_action(*actions)


def do_in_parallel(*actions: Action) -> DefaultAction:
    return _parallel_action(*actions)


def conditional(*, parallel: bool = False) -> _ConditionalContext:
    return _ConditionalContext(parallel=parallel)


def when(condition: object, *, parallel: bool | None = None) -> _BranchContext:
    expr = ensure_expr(condition)
    if active_build_session():
        return _BranchContext(expr, parallel=parallel)
    return cast(_BranchContext, _WhenBranchBuilder(None, expr))


def otherwise(*, parallel: bool | None = None) -> _BranchContext:
    return _BranchContext(None, parallel=parallel, otherwise=True)


def _iterable_source_for(source: object) -> IterableSource:
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
    source: object, *, loop_parallel: bool = False, block_parallel: bool = False
) -> _ForEachContext:
    return _ForEachContext(
        _iterable_source_for(source),
        loop_parallel=loop_parallel,
        block_parallel=block_parallel,
    )


def emit_event(writer: EventWriterProxy, event: object) -> DefaultAction:
    if not isinstance(writer, EventWriterProxy):
        raise SystemPlanError("ecs.emit_event() expects an ecs.EventWriter[...] parameter.")
    return DefaultAction("emit_event", event_writer=writer, event_value=event)


def _validate_actions(actions: tuple[Action, ...]) -> None:
    for action in actions:
        if not isinstance(action, Action):
            raise SystemPlanError(f"Expected ECS Action, got {type(action).__name__}.")


def _explain_action(action: Action, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    if isinstance(action, DefaultAction):
        if action.kind == "set" and action.target is not None:
            target = f"{action.target.component_type.__name__}.{action.target.field_name}"
            if action.value is None:
                return [f"{prefix}set {target}"]
            lines = [f"{prefix}set {target} <- {_explain_expr(action.value)}"]
            lines.extend(_explain_expr_details(action.value, indent + 1))
            return lines
        if action.kind == "sequence":
            lines = [f"{prefix}do_in_order"]
            for child in action.children:
                lines.extend(_explain_action(child, indent + 1))
            return lines
        if action.kind == "parallel":
            lines = [f"{prefix}do_in_parallel"]
            for child in action.children:
                lines.extend(_explain_action(child, indent + 1))
            return lines
        if action.kind == "udf" and action.udf is not None:
            return [f"{prefix}udf {action.udf.function.__name__}"]
        if action.kind == "emit_event" and action.event_writer is not None:
            return [f"{prefix}emit_event {action.event_writer.event_type.__name__}"]
        if (
            action.kind in {"add_component", "remove_component"}
            and action.component_type is not None
        ):
            query = action.entity_query.name if action.entity_query is not None else "?"
            return [f"{prefix}{action.kind} {query}.{action.component_type.__name__}"]
        if action.kind in {"add_tag", "remove_tag"}:
            query = action.entity_query.name if action.entity_query is not None else "?"
            return [f"{prefix}{action.kind} {query}.{action.tag}"]
        if action.kind == "despawn":
            query = action.entity_query.name if action.entity_query is not None else "?"
            return [f"{prefix}despawn {query}"]
        if action.kind == "noop":
            return [f"{prefix}noop"]
        return [f"{prefix}{action.kind}"]
    if isinstance(action, WhenAction):
        lines = [f"{prefix}when_chain"]
        for index, (condition, branch) in enumerate(action.branches, start=1):
            lines.append(f"{prefix}  when[{index}] {_explain_expr(condition)}")
            lines.extend(_explain_expr_details(condition, indent + 2))
            lines.extend(_explain_action(branch, indent + 2))
        if action.otherwise_action is not None:
            lines.append(f"{prefix}  otherwise")
            lines.extend(_explain_action(action.otherwise_action, indent + 2))
        return lines
    if isinstance(action, ForEachAction):
        source = type(action.source).__name__.removesuffix("Source")
        lines = [f"{prefix}for_each {source} mode={action.mode}"]
        if isinstance(action.source, ExpressionIterableSource):
            lines.append(f"{prefix}  source {_explain_expr(action.source.expression)}")
            lines.extend(_explain_expr_details(action.source.expression, indent + 1))
        lines.extend(_explain_action(action.body, indent + 1))
        return lines
    return [f"{prefix}{type(action).__name__}"]


def _explain_expr(expr: Expression) -> str:
    if isinstance(expr, LiteralExpression):
        return repr(expr.value)
    if isinstance(expr, FieldExpression):
        return f"{_source_name(expr.source)}.{expr.component_type.__name__}.{expr.field_name}"
    if isinstance(expr, EntityExpression):
        return f"{expr.query.name}.entity"
    if isinstance(expr, UnaryExpression):
        op = "~" if expr.op == "not" else expr.op
        return f"({op}{_explain_expr(expr.operand)})"
    if isinstance(expr, BinaryExpression):
        return f"({_explain_expr(expr.left)} {expr.op} {_explain_expr(expr.right)})"
    if isinstance(expr, AttributeExpression):
        return f"{_explain_expr(expr.base)}.{expr.attribute}"
    if isinstance(expr, FunctionExpression):
        args = ", ".join(_explain_expr(arg) for arg in expr.args)
        return f"{expr.name}({args})"
    if isinstance(expr, DeltatimeExpression):
        return "dt()"
    if isinstance(expr, KeyDownExpression):
        return f"key_is_down({expr.key!r})"
    if isinstance(expr, GroupedAnyExpression):
        return f"group_by({expr.query.name}).any({_explain_expr(expr.expression)})"
    if isinstance(expr, GroupedValueAggregateExpression):
        value = "" if expr.value is None else f", value={_explain_expr(expr.value)}"
        return f"group_by({expr.query.name}).{expr.kind}({_explain_expr(expr.expression)}{value})"
    if isinstance(expr, ExistsExpression):
        return f"exists({expr.query.name}).where({_explain_expr(expr.predicate)})"
    spatial = _explain_spatial_expr(expr)
    if spatial is not None:
        return spatial
    return type(expr).__name__


def _source_name(source: QueryProxy | ResourceProxy) -> str:
    if isinstance(source, QueryProxy):
        return source.name
    mode = "ResMut" if source.mutable else "Res"
    return f"{mode}({source.name})"


def _explain_expr_details(expr: Expression, indent: int) -> list[str]:
    prefix = "  " * indent
    relations = _collect_spatial_relations(expr)
    return [f"{prefix}{_explain_spatial_relation(relation)}" for relation in relations]


def _explain_spatial_expr(expr: Expression) -> str | None:
    from gummysnake.ecs.spatial import SpatialAggregateExpression, SpatialMetadataExpression

    if isinstance(expr, SpatialAggregateExpression):
        value = "" if expr.value is None else f", value={_explain_expr(expr.value)}"
        return f"spatial.{expr.kind}({expr.relation.name or expr.relation.item.name}{value})"
    if isinstance(expr, SpatialMetadataExpression):
        relation_name = expr.relation.name or expr.relation.item.name
        if expr.kind == "delta" and expr.axis is not None:
            axis = "xyz"[expr.axis]
            return f"spatial.{relation_name}.delta.{axis}"
        return f"spatial.{relation_name}.{expr.kind}"
    return None


def _collect_spatial_relations(expr: Expression) -> tuple[object, ...]:
    from gummysnake.ecs.spatial import SpatialAggregateExpression, SpatialMetadataExpression

    found: list[object] = []
    seen: builtins.set[int] = builtins.set()

    def add_relation(relation: object) -> None:
        key = id(relation)
        if key not in seen:
            seen.add(key)
            found.append(relation)

    def walk(node: Expression) -> None:
        if isinstance(node, SpatialAggregateExpression):
            add_relation(node.relation)
            if node.value is not None:
                walk(node.value)
            return
        if isinstance(node, SpatialMetadataExpression):
            add_relation(node.relation)
            return
        if isinstance(node, BinaryExpression):
            walk(node.left)
            walk(node.right)
            return
        if isinstance(node, UnaryExpression):
            walk(node.operand)
            return
        if isinstance(node, FunctionExpression):
            for arg in node.args:
                walk(arg)
            return
        if isinstance(node, AttributeExpression):
            walk(node.base)
            return
        if isinstance(node, GroupedAnyExpression | GroupedValueAggregateExpression):
            walk(node.expression)
            if node.value is not None:
                walk(node.value)
            return
        if isinstance(node, ExistsExpression):
            walk(node.predicate)

    walk(expr)
    return tuple(found)


def _explain_spatial_relation(relation: object) -> str:
    algorithm = getattr(relation, "algorithm", None)
    kind = getattr(algorithm, "kind", type(algorithm).__name__ if algorithm is not None else "none")
    name = getattr(relation, "name", None) or getattr(
        getattr(relation, "item", None), "name", "relation"
    )
    dimensions = getattr(relation, "dimensions", "?")
    origin = getattr(getattr(relation, "origin", None), "name", "?")
    target = getattr(getattr(relation, "item", None), "name", "?")
    predicates: list[str] = []
    if getattr(relation, "radius", None) is not None:
        predicates.append("radius")
    if getattr(relation, "origin_bounds", None) is not None:
        predicates.append("aabb")
    if getattr(relation, "exact_filter", None) is not None:
        predicates.append("exact_filter")
    pair_policy = getattr(relation, "pair_policy", "all")
    predicate_text = ",".join(predicates) if predicates else "all"
    return (
        "spatial_relation "
        f"name={name} algorithm={kind} dimensions={dimensions} "
        f"origin={origin} target={target} predicates={predicate_text} "
        f"pair_policy={pair_policy}"
    )


def action_write_targets(action: Action) -> builtins.set[tuple[object, type[Any], str]]:
    targets: builtins.set[tuple[object, type[Any], str]] = builtins.set()
    if isinstance(action, DefaultAction):
        if action.kind == "set" and action.target is not None:
            targets.add(
                (action.target.source, action.target.component_type, action.target.field_name)
            )
        elif (
            action.kind in {"add_component", "remove_component"}
            and action.component_type is not None
        ):
            targets.add((action.entity_query, action.component_type, "*structural*"))
        elif action.kind in {"add_tag", "remove_tag", "despawn"}:
            targets.add((action.entity_query, object, "*structural*"))
        for child in action.children:
            targets.update(action_write_targets(child))
    elif isinstance(action, WhenAction):
        for _, branch in action.branches:
            targets.update(action_write_targets(branch))
        if action.otherwise_action is not None:
            targets.update(action_write_targets(action.otherwise_action))
    elif isinstance(action, ForEachAction):
        targets.update(action_write_targets(action.body))
    return targets


def action_query_refs(action: Action) -> builtins.set[QueryProxy]:
    refs: builtins.set[QueryProxy] = builtins.set()
    if isinstance(action, DefaultAction):
        if action.target is not None and isinstance(action.target.source, QueryProxy):
            refs.add(action.target.source)
        if action.entity_query is not None:
            refs.add(action.entity_query)
        if action.value is not None:
            refs.update(expression_queries(action.value))
        for child in action.children:
            refs.update(action_query_refs(child))
    elif isinstance(action, WhenAction):
        for condition, branch in action.branches:
            refs.update(expression_queries(condition))
            refs.update(action_query_refs(branch))
        if action.otherwise_action is not None:
            refs.update(action_query_refs(action.otherwise_action))
    elif isinstance(action, ForEachAction):
        if isinstance(action.source, ExpressionIterableSource):
            refs.update(expression_queries(action.source.expression))
        refs.update(action_query_refs(action.body))
    return refs


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
