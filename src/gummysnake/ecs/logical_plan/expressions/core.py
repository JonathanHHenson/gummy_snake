"""Core lazy ECS expression nodes and math helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from .helpers import ExpressionInput, _cached_expression_eval, ensure_expr

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.logical_plan.specifications import Query
    from gummysnake.ecs.world_facade import EcsWorld

    from .aggregates import GroupedExpression
    from .proxies import QueryProxy


type ExpressionContext = dict[object, Any]


@runtime_checkable
class OuterQueryProvider(Protocol):
    """Protocol for expressions that expose query dependencies from an outer scope."""

    def _ecs_outer_queries(self) -> set[QueryProxy]: ...


class Vector[T](list[T]):
    """Row-aligned vector materialization buffer for explicit Python UDF/system boundaries."""


class Expression:
    """Base lazy ECS expression."""

    def __class_getitem__(cls, item: object) -> type[Expression]:
        del item
        return cls

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> Any:
        """Evaluate this expression for one ECS row.

        Args:
            ctx: Query bindings and cached values for the current row.
            world: ECS world used to resolve resources, joins, and runtime state.

        Returns:
            The Python value produced by the expression.
        """

        raise NotImplementedError

    __hash__ = object.__hash__

    def __bool__(self) -> bool:
        raise TypeError(
            "ECS expressions are lazy query-plan values. Use '&'/'|'/'~' or "
            "ecs.all_of()/ecs.any_of(); Python 'and'/'or' and chained comparisons "
            "cannot build ECS plans."
        )

    def __add__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("add", self, ensure_expr(other))

    def __radd__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("add", ensure_expr(other), self)

    def __sub__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("sub", self, ensure_expr(other))

    def __rsub__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("sub", ensure_expr(other), self)

    def __mul__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("mul", self, ensure_expr(other))

    def __rmul__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("mul", ensure_expr(other), self)

    def __truediv__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("truediv", self, ensure_expr(other))

    def __rtruediv__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("truediv", ensure_expr(other), self)

    def __floordiv__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("floordiv", self, ensure_expr(other))

    def __mod__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("mod", self, ensure_expr(other))

    def __pow__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("pow", self, ensure_expr(other))

    def __rpow__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("pow", ensure_expr(other), self)

    def __neg__(self) -> Expression:
        return UnaryExpression("neg", self)

    def __lt__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("lt", self, ensure_expr(other))

    def __le__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("le", self, ensure_expr(other))

    def __gt__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("gt", self, ensure_expr(other))

    def __ge__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("ge", self, ensure_expr(other))

    def __eq__(self, other: ExpressionInput) -> Expression:  # type: ignore[override]
        return BinaryExpression("eq", self, ensure_expr(other))

    def __ne__(self, other: ExpressionInput) -> Expression:  # type: ignore[override]
        return BinaryExpression("ne", self, ensure_expr(other))

    def __and__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("and", self, ensure_expr(other))

    def __rand__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("and", ensure_expr(other), self)

    def __or__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("or", self, ensure_expr(other))

    def __ror__(self, other: ExpressionInput) -> Expression:
        return BinaryExpression("or", ensure_expr(other), self)

    def __invert__(self) -> Expression:
        return UnaryExpression("not", self)

    def sqrt(self) -> Expression:
        """Return a lazy expression for the square root of this numeric value."""

        return FunctionExpression("sqrt", (self,))

    def abs(self) -> Expression:
        """Return a lazy expression for the absolute value of this numeric value."""

        return FunctionExpression("abs", (self,))

    def sin(self) -> Expression:
        """Return a lazy expression for the sine of this numeric value in radians."""

        return FunctionExpression("sin", (self,))

    def cos(self) -> Expression:
        """Return a lazy expression for the cosine of this numeric value in radians."""

        return FunctionExpression("cos", (self,))

    def floor(self) -> Expression:
        """Return a lazy expression rounded down to the nearest whole number."""

        return FunctionExpression("floor", (self,))

    def ceil(self) -> Expression:
        """Return a lazy expression rounded up to the nearest whole number."""

        return FunctionExpression("ceil", (self,))

    def clamp(self, minimum: ExpressionInput, maximum: ExpressionInput) -> Expression:
        """Return a lazy expression limited to a minimum and maximum value.

        Args:
            minimum: Lowest allowed value or expression.
            maximum: Highest allowed value or expression.

        Returns:
            An expression that stays within the inclusive range.
        """

        return FunctionExpression("clamp", (self, ensure_expr(minimum), ensure_expr(maximum)))

    def clamp_min(self, minimum: ExpressionInput) -> Expression:
        """Return a lazy expression that is never lower than ``minimum``.

        Args:
            minimum: Lowest allowed value or expression.

        Returns:
            An expression using this value when it is greater than ``minimum``.
        """

        return FunctionExpression("max", (self, ensure_expr(minimum)))

    def clamp_max(self, maximum: ExpressionInput) -> Expression:
        """Return a lazy expression that is never higher than ``maximum``.

        Args:
            maximum: Highest allowed value or expression.

        Returns:
            An expression using this value when it is less than ``maximum``.
        """

        return FunctionExpression("min", (self, ensure_expr(maximum)))

    def group_by(self, query: QueryProxy | Query) -> GroupedExpression:
        """Group aggregate results by the entity currently bound to ``query``.

        Args:
            query: Query proxy whose current entity should identify each group.

        Returns:
            A grouped expression with helpers such as ``count()``, ``sum()``, and ``mean()``.
        """

        from .aggregates import GroupedExpression
        from .proxies import QueryProxy

        return GroupedExpression(self, cast(QueryProxy, query))

    def __getattr__(self, attribute: str) -> Expression:
        if attribute.startswith("__"):
            raise AttributeError(attribute)
        return AttributeExpression(self, attribute)


@dataclass(frozen=True, eq=False)
class LiteralExpression(Expression):
    """Expression node that stores a literal Python value."""

    value: Any

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> Any:
        """Return the stored literal value for the current ECS row.

        Args:
            ctx: Query bindings for the row; ignored because literals are constant.
            world: ECS world for the row; ignored because literals are constant.

        Returns:
            The literal Python value stored in this node.
        """

        del ctx, world
        return self.value


@dataclass(frozen=True, eq=False)
class UnaryExpression(Expression):
    """Expression node for unary operators such as negation and logical not."""

    op: str
    operand: Expression

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> Any:
        """Evaluate the operand and apply this unary operator.

        Args:
            ctx: Query bindings and cache for the current row.
            world: ECS world used by the operand expression.

        Returns:
            The negated value or boolean inverse, depending on ``op``.
        """

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
    """Expression node for arithmetic, comparison, and boolean operators."""

    op: str
    left: Expression
    right: Expression

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> Any:
        """Evaluate both sides and apply this binary operator.

        Args:
            ctx: Query bindings and cache for the current row.
            world: ECS world used by child expressions.

        Returns:
            The arithmetic, comparison, or boolean result for this row.
        """

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
    """Expression node that reads an attribute from another expression value."""

    base: Expression
    attribute: str

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> Any:
        """Read an attribute from the evaluated base expression.

        Args:
            ctx: Query bindings and cache for the current row.
            world: ECS world used by the base expression.

        Returns:
            The attribute value from the base expression result.
        """

        return _cached_expression_eval(
            self, ctx, world, lambda: getattr(self.base.eval(ctx, world), self.attribute)
        )


@dataclass(frozen=True, eq=False)
class FunctionExpression(Expression):
    """Expression node for built-in numeric helper functions."""

    name: str
    args: tuple[Expression, ...]

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> Any:
        """Evaluate the arguments and apply this built-in helper function.

        Args:
            ctx: Query bindings and cache for the current row.
            world: ECS world used by argument expressions.

        Returns:
            The numeric helper result for this row.
        """

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
    """Expression node that reads the current sketch delta time."""

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> float:
        """Return the sketch delta time for the current ECS run.

        Args:
            ctx: Query bindings for the row; ignored by this expression.
            world: ECS world whose sketch context stores the frame delta time.

        Returns:
            Seconds elapsed since the previous frame, or ``0.0`` without a context.
        """

        del ctx
        context = world.context
        if context is None:
            return 0.0
        return float(context.delta_time)


@dataclass(frozen=True, eq=False)
class KeyDownExpression(Expression):
    """Expression node that checks whether a keyboard key is held."""

    key: int | str

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> bool:
        """Return whether the configured key is currently held down.

        Args:
            ctx: Query bindings for the row; ignored by this expression.
            world: ECS world whose sketch context owns keyboard state.

        Returns:
            ``True`` when the key is down for the current frame.
        """

        del ctx
        context = world.context
        return False if context is None else bool(context.key_is_down(self.key))


__all__ = [
    "AttributeExpression",
    "BinaryExpression",
    "DeltatimeExpression",
    "Expression",
    "ExpressionContext",
    "FunctionExpression",
    "KeyDownExpression",
    "LiteralExpression",
    "OuterQueryProvider",
    "UnaryExpression",
    "Vector",
]
