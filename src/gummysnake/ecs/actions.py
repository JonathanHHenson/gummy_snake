"""ECS action tree builders and execution."""

from __future__ import annotations

import builtins
import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
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
class _WhenBranchBuilder:
    chain: WhenAction | None
    condition: Expression

    def do(self, *actions: Action) -> WhenAction:
        action = do(*actions)
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
        self.chain.otherwise_action = do(*actions)
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
        return ForEachAction(self.source, do(*actions), mode="sequence")

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
class UdfDefinition:
    function: Callable[..., Any]
    return_annotation: object
    reads: tuple[type[Any], ...] = ()
    writes: tuple[type[Any], ...] = ()
    structural: bool = False
    side_effects: bool = False

    def __call__(self, *args: object) -> DefaultAction | UdfIterableSource:
        if _is_iterable_annotation(self.return_annotation):
            return UdfIterableSource(self, tuple(args))
        return DefaultAction("udf", udf=self, udf_args=tuple(args))

    def call_runtime(self, world: EcsWorld, args: tuple[object, ...]) -> Any:
        materialized = [world.materialize_udf_arg(arg) for arg in args]
        return self.function(*materialized)

    def execute_action(self, world: EcsWorld, args: tuple[object, ...]) -> None:
        self.call_runtime(world, args)
        world._diagnostics["ecs_udf_calls"] += 1


def _is_iterable_annotation(annotation: object) -> bool:
    origin = get_origin(annotation)
    if origin is None:
        return False
    return origin in {Iterable, list, tuple} or getattr(origin, "__name__", "") in {
        "Iterable",
        "Iterator",
        "Generator",
    }


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
) -> Callable[[Callable[..., Any]], UdfDefinition]: ...


def udf(
    function: Callable[..., Any] | None = None,
    *,
    reads: Iterable[type[Any]] = (),
    writes: Iterable[type[Any]] = (),
    structural: bool = False,
    side_effects: bool = False,
) -> Callable[[Callable[..., Any]], UdfDefinition] | UdfDefinition:
    def decorate(callback: Callable[..., Any]) -> UdfDefinition:
        hints = get_type_hints(callback, include_extras=True)
        signature = inspect.signature(callback)
        for parameter in signature.parameters.values():
            if parameter.name not in hints:
                raise SystemPlanError(
                    f"ECS UDF {callback.__name__} parameter {parameter.name!r} needs a "
                    "type annotation."
                )
        if "return" not in hints:
            raise SystemPlanError(f"ECS UDF {callback.__name__} needs a return annotation.")
        return UdfDefinition(
            callback,
            hints["return"],
            reads=tuple(reads),
            writes=tuple(writes),
            structural=structural,
            side_effects=side_effects,
        )

    if function is not None:
        return decorate(function)
    return decorate


def set(target: FieldExpression, value: object) -> DefaultAction:
    if not isinstance(target, FieldExpression):
        raise SystemPlanError("ecs.set() target must be a component or resource field expression.")
    return DefaultAction("set", target=target, value=ensure_expr(value))


def do(*actions: Action) -> DefaultAction:
    if not actions:
        return DefaultAction("noop")
    _validate_actions(actions)
    return DefaultAction("sequence", children=tuple(actions))


def do_in_order(*actions: Action) -> DefaultAction:
    return do(*actions)


def do_in_parallel(*actions: Action) -> DefaultAction:
    _validate_actions(actions)
    return DefaultAction("parallel", children=tuple(actions))


def when(condition: object) -> _WhenBranchBuilder:
    return _WhenBranchBuilder(None, ensure_expr(condition))


def for_each(source: object) -> _ForEachBuilder:
    if isinstance(source, UdfIterableSource):
        return _ForEachBuilder(source)
    if isinstance(source, EventReaderProxy):
        return _ForEachBuilder(EventIterableSource(source))
    if isinstance(source, Expression):
        return _ForEachBuilder(ExpressionIterableSource(source))
    raise SystemPlanError(
        "ecs.for_each() accepts annotated @ecs.udf iterable sources or list/vector "
        "field expressions."
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
    "EventIterableSource",
    "ExpressionIterableSource",
    "ForEachAction",
    "IterableSource",
    "SystemPlan",
    "UdfDefinition",
    "WhenAction",
    "do",
    "do_in_order",
    "do_in_parallel",
    "emit_event",
    "for_each",
    "set",
    "udf",
    "when",
]
