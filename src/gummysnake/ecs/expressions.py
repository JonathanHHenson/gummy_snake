"""Lazy ECS expression objects used by system actions."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, is_dataclass
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Protocol,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    runtime_checkable,
)

if TYPE_CHECKING:
    from gummysnake.ecs.world import EcsWorld, EntityView


@runtime_checkable
class OuterQueryProvider(Protocol):
    def _ecs_outer_queries(self) -> set[QueryProxy]: ...


class Vector(list[Any]):
    """Row-aligned vector materialization buffer for explicit Python UDF/system boundaries."""


class Expression:
    """Base lazy expression."""

    def __class_getitem__(cls, item: object) -> type[Expression]:
        del item
        return cls

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        raise NotImplementedError

    __hash__ = object.__hash__

    def __bool__(self) -> bool:
        raise TypeError(
            "ECS expressions are lazy query-plan values. Use '&'/'|'/'~' or "
            "ecs.all_of()/ecs.any_of(); Python 'and'/'or' and chained comparisons "
            "cannot build ECS plans."
        )

    def __add__(self, other: object) -> Expression:
        return BinaryExpression("add", self, ensure_expr(other))

    def __radd__(self, other: object) -> Expression:
        return BinaryExpression("add", ensure_expr(other), self)

    def __sub__(self, other: object) -> Expression:
        return BinaryExpression("sub", self, ensure_expr(other))

    def __rsub__(self, other: object) -> Expression:
        return BinaryExpression("sub", ensure_expr(other), self)

    def __mul__(self, other: object) -> Expression:
        return BinaryExpression("mul", self, ensure_expr(other))

    def __rmul__(self, other: object) -> Expression:
        return BinaryExpression("mul", ensure_expr(other), self)

    def __truediv__(self, other: object) -> Expression:
        return BinaryExpression("truediv", self, ensure_expr(other))

    def __rtruediv__(self, other: object) -> Expression:
        return BinaryExpression("truediv", ensure_expr(other), self)

    def __floordiv__(self, other: object) -> Expression:
        return BinaryExpression("floordiv", self, ensure_expr(other))

    def __mod__(self, other: object) -> Expression:
        return BinaryExpression("mod", self, ensure_expr(other))

    def __pow__(self, other: object) -> Expression:
        return BinaryExpression("pow", self, ensure_expr(other))

    def __rpow__(self, other: object) -> Expression:
        return BinaryExpression("pow", ensure_expr(other), self)

    def __neg__(self) -> Expression:
        return UnaryExpression("neg", self)

    def __lt__(self, other: object) -> Expression:
        return BinaryExpression("lt", self, ensure_expr(other))

    def __le__(self, other: object) -> Expression:
        return BinaryExpression("le", self, ensure_expr(other))

    def __gt__(self, other: object) -> Expression:
        return BinaryExpression("gt", self, ensure_expr(other))

    def __ge__(self, other: object) -> Expression:
        return BinaryExpression("ge", self, ensure_expr(other))

    def __eq__(self, other: object) -> Expression:  # type: ignore[override]
        return BinaryExpression("eq", self, ensure_expr(other))

    def __ne__(self, other: object) -> Expression:  # type: ignore[override]
        return BinaryExpression("ne", self, ensure_expr(other))

    def __and__(self, other: object) -> Expression:
        return BinaryExpression("and", self, ensure_expr(other))

    def __rand__(self, other: object) -> Expression:
        return BinaryExpression("and", ensure_expr(other), self)

    def __or__(self, other: object) -> Expression:
        return BinaryExpression("or", self, ensure_expr(other))

    def __ror__(self, other: object) -> Expression:
        return BinaryExpression("or", ensure_expr(other), self)

    def __invert__(self) -> Expression:
        return UnaryExpression("not", self)

    def sqrt(self) -> Expression:
        return FunctionExpression("sqrt", (self,))

    def abs(self) -> Expression:
        return FunctionExpression("abs", (self,))

    def sin(self) -> Expression:
        return FunctionExpression("sin", (self,))

    def cos(self) -> Expression:
        return FunctionExpression("cos", (self,))

    def floor(self) -> Expression:
        return FunctionExpression("floor", (self,))

    def ceil(self) -> Expression:
        return FunctionExpression("ceil", (self,))

    def clamp(self, minimum: object, maximum: object) -> Expression:
        return FunctionExpression("clamp", (self, ensure_expr(minimum), ensure_expr(maximum)))

    def clamp_min(self, minimum: object) -> Expression:
        return FunctionExpression("max", (self, ensure_expr(minimum)))

    def clamp_max(self, maximum: object) -> Expression:
        return FunctionExpression("min", (self, ensure_expr(maximum)))

    def group_by(self, query: object) -> GroupedExpression:
        return GroupedExpression(self, cast(QueryProxy, query))

    def __getattr__(self, attribute: str) -> Expression:
        if attribute.startswith("__"):
            raise AttributeError(attribute)
        return AttributeExpression(self, attribute)


@dataclass(frozen=True, eq=False)
class LiteralExpression(Expression):
    value: Any

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        del ctx, world
        return self.value


@dataclass(frozen=True, eq=False)
class UnaryExpression(Expression):
    op: str
    operand: Expression

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        def compute() -> Any:
            value = self.operand.eval(ctx, world)
            if self.op == "neg":
                return -value
            if self.op == "not":
                return not bool(value)
            raise ValueError(f"Unsupported ECS unary op {self.op!r}")

        return _cached_expression_eval(self, ctx, world, compute)


@dataclass(frozen=True, eq=False)
class BinaryExpression(Expression):
    op: str
    left: Expression
    right: Expression

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        def compute() -> Any:
            left = self.left.eval(ctx, world)
            if self.op == "and":
                return bool(left) and bool(self.right.eval(ctx, world))
            if self.op == "or":
                return bool(left) or bool(self.right.eval(ctx, world))
            right = self.right.eval(ctx, world)
            if self.op == "add":
                return left + right
            if self.op == "sub":
                return left - right
            if self.op == "mul":
                return left * right
            if self.op == "truediv":
                return left / right
            if self.op == "floordiv":
                return left // right
            if self.op == "mod":
                return left % right
            if self.op == "pow":
                return left**right
            if self.op == "lt":
                return left < right
            if self.op == "le":
                return left <= right
            if self.op == "gt":
                return left > right
            if self.op == "ge":
                return left >= right
            if self.op == "eq":
                return left == right
            if self.op == "ne":
                return left != right
            raise ValueError(f"Unsupported ECS binary op {self.op!r}")

        return _cached_expression_eval(self, ctx, world, compute)


@dataclass(frozen=True, eq=False)
class AttributeExpression(Expression):
    base: Expression
    attribute: str

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        return _cached_expression_eval(
            self, ctx, world, lambda: getattr(self.base.eval(ctx, world), self.attribute)
        )


@dataclass(frozen=True, eq=False)
class FunctionExpression(Expression):
    name: str
    args: tuple[Expression, ...]

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        def compute() -> Any:
            values = [arg.eval(ctx, world) for arg in self.args]
            if self.name == "sqrt":
                return math.sqrt(values[0])
            if self.name == "abs":
                return abs(values[0])
            if self.name == "sin":
                return math.sin(values[0])
            if self.name == "cos":
                return math.cos(values[0])
            if self.name == "floor":
                return math.floor(values[0])
            if self.name == "ceil":
                return math.ceil(values[0])
            if self.name == "min":
                return min(values)
            if self.name == "max":
                return max(values)
            if self.name == "clamp":
                value, minimum, maximum = values
                return min(max(value, minimum), maximum)
            raise ValueError(f"Unsupported ECS function {self.name!r}")

        return _cached_expression_eval(self, ctx, world, compute)


@dataclass(frozen=True, eq=False)
class DeltatimeExpression(Expression):
    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> float:
        del ctx
        context = world.context
        if context is None:
            return 0.0
        return float(context.delta_time)


@dataclass(frozen=True, eq=False)
class KeyDownExpression(Expression):
    key: int | str

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> bool:
        del ctx
        context = world.context
        return False if context is None else bool(context.key_is_down(self.key))


@dataclass(frozen=True, eq=False)
class QueryProxy:
    name: str
    spec: object

    @property
    def ctx(self) -> QueryProxy:
        return self

    @property
    def entity(self) -> EntityExpression:
        return EntityExpression(self)

    def __getitem__(self, component_type: type[Any]) -> ComponentExpressionProxy:
        return ComponentExpressionProxy(self, component_type)

    def as_iter(self, *component_types: type[Any]) -> object:
        from gummysnake.ecs.actions import EntityIteratorSource
        from gummysnake.ecs.specs import QuerySpec
        from gummysnake.exceptions import SystemPlanError

        if not isinstance(self.spec, QuerySpec):
            raise SystemPlanError(
                "Query.as_iter() requires a concrete ecs.Query[...] specification."
            )
        available = {term for term in self.spec.terms if isinstance(term, type)}
        for component_type in component_types:
            if component_type not in available:
                raise SystemPlanError(
                    f"Query.as_iter() projection {component_type.__name__} is not present "
                    f"in query {self.name!r}."
                )
        return EntityIteratorSource(self, tuple(component_types))

    def __repr__(self) -> str:
        return f"QueryProxy({self.name})"


@dataclass(frozen=True, eq=False)
class ResourceProxy:
    name: str
    resource_type: type[Any]
    mutable: bool = False

    def __getitem__(self, resource_type: type[Any]) -> ComponentExpressionProxy:
        if resource_type is not self.resource_type:
            raise KeyError(
                f"Resource parameter {self.name!r} was declared for "
                f"{self.resource_type.__name__}, not {resource_type.__name__}."
            )
        return ComponentExpressionProxy(self, resource_type)

    def __repr__(self) -> str:
        mode = "ResMut" if self.mutable else "Res"
        return f"{mode}({self.name})"


@dataclass(frozen=True, eq=False)
class ComponentExpressionProxy:
    source: QueryProxy | ResourceProxy
    component_type: type[Any]

    def __getattr__(self, field_name: str) -> FieldExpression:
        if field_name.startswith("__"):
            raise AttributeError(field_name)
        return FieldExpression(self.source, self.component_type, field_name)


@dataclass(frozen=True, eq=False)
class FieldExpression(Expression):
    source: QueryProxy | ResourceProxy
    component_type: type[Any]
    field_name: str

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        if isinstance(self.source, QueryProxy):
            entity = ctx[self.source]
            return getattr(entity[self.component_type], self.field_name)
        value = world.get_resource(self.component_type)
        return getattr(value, self.field_name)

    def set_value(self, ctx: dict[object, Any], world: EcsWorld, value: Any) -> None:
        if isinstance(self.source, QueryProxy):
            entity = ctx[self.source]
            setattr(entity[self.component_type], self.field_name, value)
            world._sync_component_field_to_rust(
                entity.entity, self.component_type, self.field_name, value
            )
            world._note_field_update(entity.entity, self.component_type)
            return
        if not self.source.mutable:
            from gummysnake.exceptions import SystemPlanError

            raise SystemPlanError(
                f"Resource parameter {self.source.name!r} is read-only; use ecs.ResMut[...] "
                f"to write {self.component_type.__name__}.{self.field_name}."
            )
        resource = world.get_resource(self.component_type)
        setattr(resource, self.field_name, value)
        world._sync_resource_field_to_rust(self.component_type, self.field_name, value)
        world._note_resource_update()

    def set_to(self, value: object) -> None:
        """Append a logical field assignment to the active ECS system build block."""

        self._ensure_writable()
        from gummysnake.ecs.actions import append_action, set

        append_action(
            set(self, value), operation=f"{self.component_type.__name__}.{self.field_name}.set_to()"
        )

    def increase_by(self, amount: object) -> None:
        """Append ``field = field + amount`` to the active ECS system build block."""

        self._ensure_numeric_update(amount, "increase_by")
        self.set_to(self + amount)

    def decrease_by(self, amount: object) -> None:
        """Append ``field = field - amount`` to the active ECS system build block."""

        self._ensure_numeric_update(amount, "decrease_by")
        self.set_to(self - amount)

    def _ensure_writable(self) -> None:
        from gummysnake.exceptions import SystemPlanError

        if isinstance(self.source, ResourceProxy) and not self.source.mutable:
            raise SystemPlanError(
                f"Resource parameter {self.source.name!r} is read-only; use "
                f"ecs.ResMut[{self.component_type.__name__}] to write "
                f"{self.component_type.__name__}.{self.field_name}."
            )

    def _ensure_numeric_update(self, amount: object, method: str) -> None:
        from gummysnake.exceptions import SystemPlanError

        if not _field_annotation_is_numeric(self.component_type, self.field_name):
            raise SystemPlanError(
                f"{self.component_type.__name__}.{self.field_name}.{method}() requires "
                "a numeric field."
            )
        if isinstance(amount, bool | str):
            raise SystemPlanError(f"{method}() requires a numeric expression or literal amount.")


@dataclass(frozen=True, eq=False)
class EntityExpression(Expression):
    query: QueryProxy

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> EntityView:
        del world
        return ctx[self.query]

    def add_component(self, component: object | type[Any]) -> None:
        from gummysnake.ecs.actions import add_component_action, append_action

        append_action(
            add_component_action(self, component), operation="query.entity.add_component()"
        )

    def remove_component(self, component_type: type[Any]) -> None:
        from gummysnake.ecs.actions import append_action, remove_component_action

        append_action(
            remove_component_action(self, component_type),
            operation="query.entity.remove_component()",
        )

    def add_tag(self, tag: object) -> None:
        from gummysnake.ecs.actions import add_tag_action, append_action

        append_action(add_tag_action(self, tag), operation="query.entity.add_tag()")

    def remove_tag(self, tag: object) -> None:
        from gummysnake.ecs.actions import append_action, remove_tag_action

        append_action(remove_tag_action(self, tag), operation="query.entity.remove_tag()")

    def despawn(self) -> None:
        from gummysnake.ecs.actions import append_action, despawn_action

        append_action(despawn_action(self), operation="query.entity.despawn()")


def _field_annotation_is_numeric(component_type: type[Any], field_name: str) -> bool:
    try:
        annotations = get_type_hints(component_type, include_extras=True)
    except Exception:
        annotations = getattr(component_type, "__annotations__", {})
    annotation = annotations.get(field_name)
    if annotation is None:
        return True
    origin = get_origin(annotation)
    if origin is Annotated:
        base, *metadata = get_args(annotation)
        if any(getattr(item, "python_type", None) in {int, float} for item in metadata):
            return True
        annotation = base
        origin = get_origin(annotation)
    if annotation in {int, float}:
        return True
    if origin in {tuple, list}:
        return False
    return False


@dataclass(frozen=True, eq=False)
class GroupedExpression(Expression):
    expression: Expression
    query: QueryProxy

    def any(self) -> GroupedAnyExpression:
        return GroupedAnyExpression(self.expression, self.query)

    def count(self) -> GroupedValueAggregateExpression:
        return GroupedValueAggregateExpression("count", self.expression, self.query)

    def sum(self, value: object | None = None) -> GroupedValueAggregateExpression:
        return GroupedValueAggregateExpression(
            "sum", self.expression, self.query, ensure_expr(1 if value is None else value)
        )

    def min(
        self, value: object, *, default: object | None = None
    ) -> GroupedValueAggregateExpression:
        return GroupedValueAggregateExpression(
            "min", self.expression, self.query, ensure_expr(value), default
        )

    def max(
        self, value: object, *, default: object | None = None
    ) -> GroupedValueAggregateExpression:
        return GroupedValueAggregateExpression(
            "max", self.expression, self.query, ensure_expr(value), default
        )

    def mean(
        self, value: object, *, default: object | None = None
    ) -> GroupedValueAggregateExpression:
        return GroupedValueAggregateExpression(
            "mean", self.expression, self.query, ensure_expr(value), default
        )


@dataclass(frozen=True, eq=False)
class GroupedAnyExpression(Expression):
    expression: Expression
    query: QueryProxy

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> bool:
        if self.query not in ctx:
            return False
        target_entity = ctx[self.query]
        for joined in world.iter_join_contexts_for(ctx, self.expression):
            if joined.get(self.query) == target_entity and bool(
                self.expression.eval(joined, world)
            ):
                return True
        return False


@dataclass(frozen=True, eq=False)
class GroupedValueAggregateExpression(Expression):
    kind: str
    expression: Expression
    query: QueryProxy
    value: Expression | None = None
    default: object | None = None

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> Any:
        if self.query not in ctx:
            if self.kind == "count":
                return 0
            if self.default is not None:
                return self.default
            if self.kind == "sum":
                return 0
            raise ValueError(f"Grouped {self.kind} aggregate is empty and no default was provided.")
        target_entity = ctx[self.query]
        values: list[Any] = []
        count = 0
        for joined in world.iter_join_contexts_for(ctx, self.expression):
            if joined.get(self.query) != target_entity or not bool(
                self.expression.eval(joined, world)
            ):
                continue
            count += 1
            if self.value is not None:
                values.append(self.value.eval(joined, world))
        if self.kind == "count":
            return count
        if self.kind == "sum":
            return sum(values) if values else 0
        if self.kind == "min":
            if values:
                return min(values)
            if self.default is not None:
                return self.default
            raise ValueError("Grouped min aggregate is empty and no default was provided.")
        if self.kind == "max":
            if values:
                return max(values)
            if self.default is not None:
                return self.default
            raise ValueError("Grouped max aggregate is empty and no default was provided.")
        if self.kind == "mean":
            if values:
                return sum(values) / len(values)
            if self.default is not None:
                return self.default
            raise ValueError("Grouped mean aggregate is empty and no default was provided.")
        raise ValueError(f"Unsupported grouped aggregate {self.kind!r}.")


@dataclass(frozen=True, eq=False)
class ExistsExpression(Expression):
    query: QueryProxy
    predicate: Expression

    def eval(self, ctx: dict[object, Any], world: EcsWorld) -> bool:
        for joined in world.iter_join_contexts_for(ctx, self.predicate, include_query=self.query):
            if bool(self.predicate.eval(joined, world)):
                return True
        return False


@dataclass(frozen=True)
class ExistsBuilder:
    query: QueryProxy

    def where(self, predicate: Expression) -> ExistsExpression:
        return ExistsExpression(self.query, ensure_expr(predicate))


def _cached_expression_eval(
    expr: Expression,
    ctx: dict[object, Any],
    world: EcsWorld,
    compute: Callable[[], Any],
) -> Any:
    cache = getattr(world, "_expression_eval_cache", None)
    if cache is None:
        return compute()
    key = (id(expr), _expression_context_key(ctx))
    if key in cache:
        world._diagnostics["ecs_expression_cache_hits"] += 1
        return cache[key]
    world._diagnostics["ecs_expression_cache_misses"] += 1
    result = compute()
    cache[key] = result
    return result


def _expression_context_key(ctx: dict[object, Any]) -> tuple[object, ...]:
    parts: list[tuple[object, ...]] = []
    for key, value in ctx.items():
        if hasattr(value, "entity"):
            entity = value.entity
            parts.append(
                ("entity", id(key), int(entity.world_id), int(entity.index), int(entity.generation))
            )
        else:
            parts.append(("value", id(key), _expression_value_key(value)))
    return tuple(sorted(parts))


def _expression_value_key(value: object) -> object:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if is_dataclass(value):
        return repr(value)
    return id(value)


def ensure_expr(value: object) -> Expression:
    if isinstance(value, Expression):
        return value
    return LiteralExpression(value)


def all_of(*conditions: object) -> Expression:
    if not conditions:
        return LiteralExpression(True)
    expr = ensure_expr(conditions[0])
    for condition in conditions[1:]:
        expr = expr & ensure_expr(condition)
    return expr


def any_of(*conditions: object) -> Expression:
    if not conditions:
        return LiteralExpression(False)
    expr = ensure_expr(conditions[0])
    for condition in conditions[1:]:
        expr = expr | ensure_expr(condition)
    return expr


def literal(value: object) -> Expression:
    return LiteralExpression(value)


def dt() -> Expression:
    return DeltatimeExpression()


def key_is_down(key: int | str) -> Expression:
    return KeyDownExpression(key)


def exists(query: object) -> ExistsBuilder:
    return ExistsBuilder(cast(QueryProxy, query))


def expression_queries(expr: Expression) -> set[QueryProxy]:
    found: set[QueryProxy] = set()

    def collect(node: Expression) -> set[QueryProxy]:
        if isinstance(node, FieldExpression) and isinstance(node.source, QueryProxy):
            return {node.source}
        if isinstance(node, EntityExpression):
            return {node.query}
        if isinstance(node, BinaryExpression):
            return collect(node.left) | collect(node.right)
        if isinstance(node, UnaryExpression):
            return collect(node.operand)
        if isinstance(node, FunctionExpression):
            refs: set[QueryProxy] = set()
            for arg in node.args:
                refs.update(collect(arg))
            return refs
        if isinstance(node, AttributeExpression):
            return collect(node.base)
        if isinstance(node, GroupedAnyExpression | GroupedValueAggregateExpression):
            # The grouped query is part of the outer row context. Queries used only by the
            # aggregate input are expanded inside aggregate eval(), so they must not pre-expand
            # the branch into the cross join the aggregate is meant to reduce.
            return {node.query}
        if isinstance(node, OuterQueryProvider):
            return node._ecs_outer_queries()
        if isinstance(node, ExistsExpression):
            # The exists() query is evaluated inside ExistsExpression.eval(). Keep only
            # external query references needed by its predicate in the outer row context.
            refs = collect(node.predicate)
            refs.discard(node.query)
            return refs
        return set()

    found.update(collect(expr))
    return found


def replace_query(expr: Expression, old: QueryProxy, new: QueryProxy) -> Expression:
    """Return ``expr`` with field/entity refs from one query alias replaced by another."""

    if isinstance(expr, FieldExpression) and expr.source == old:
        return FieldExpression(new, expr.component_type, expr.field_name)
    if isinstance(expr, EntityExpression) and expr.query == old:
        return EntityExpression(new)
    if isinstance(expr, BinaryExpression):
        return BinaryExpression(
            expr.op, replace_query(expr.left, old, new), replace_query(expr.right, old, new)
        )
    if isinstance(expr, UnaryExpression):
        return UnaryExpression(expr.op, replace_query(expr.operand, old, new))
    if isinstance(expr, FunctionExpression):
        return FunctionExpression(
            expr.name, tuple(replace_query(arg, old, new) for arg in expr.args)
        )
    if isinstance(expr, AttributeExpression):
        return AttributeExpression(replace_query(expr.base, old, new), expr.attribute)
    return expr


__all__ = [
    "AttributeExpression",
    "Expression",
    "FieldExpression",
    "FunctionExpression",
    "GroupedValueAggregateExpression",
    "OuterQueryProvider",
    "QueryProxy",
    "ResourceProxy",
    "all_of",
    "any_of",
    "dt",
    "exists",
    "expression_queries",
    "key_is_down",
    "literal",
    "replace_query",
]
