"""Grouped aggregate and existence expression nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gummysnake.ecs.expression_tools import ensure_expr
from gummysnake.ecs.expressions.core import Expression, ExpressionContext
from gummysnake.ecs.expressions.proxies import QueryProxy

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


@dataclass(frozen=True, eq=False)
class GroupedExpression(Expression):
    expression: Expression
    query: QueryProxy

    def any(self) -> GroupedAnyExpression:
        """Return true when any row in this group matches the source expression."""

        return GroupedAnyExpression(self.expression, self.query)

    def count(self) -> GroupedValueAggregateExpression:
        """Count matching rows in each group and return a lazy numeric aggregate."""

        return GroupedValueAggregateExpression("count", self.expression, self.query)

    def sum(self, value: object | None = None) -> GroupedValueAggregateExpression:
        """Sum ``value`` for matching rows; omitted values count each row as ``1``.

        Args:
            value: Value or expression to add for each matching row.

        Returns:
            A lazy numeric aggregate expression.
        """

        return GroupedValueAggregateExpression(
            "sum", self.expression, self.query, ensure_expr(1 if value is None else value)
        )

    def min(
        self, value: object, *, default: object | None = None
    ) -> GroupedValueAggregateExpression:
        """Return a lazy aggregate for the smallest value in each matching group.

        Args:
            value: Value or expression to compare for each matching row.
            default: Value to use when a group has no matching rows.

        Returns:
            A lazy numeric aggregate expression.
        """

        return GroupedValueAggregateExpression(
            "min", self.expression, self.query, ensure_expr(value), default
        )

    def max(
        self, value: object, *, default: object | None = None
    ) -> GroupedValueAggregateExpression:
        """Return a lazy aggregate for the largest value in each matching group.

        Args:
            value: Value or expression to compare for each matching row.
            default: Value to use when a group has no matching rows.

        Returns:
            A lazy numeric aggregate expression.
        """

        return GroupedValueAggregateExpression(
            "max", self.expression, self.query, ensure_expr(value), default
        )

    def mean(
        self, value: object, *, default: object | None = None
    ) -> GroupedValueAggregateExpression:
        """Return a lazy aggregate for the average value in each matching group.

        Args:
            value: Value or expression to average for each matching row.
            default: Value to use when a group has no matching rows.

        Returns:
            A lazy numeric aggregate expression.
        """

        return GroupedValueAggregateExpression(
            "mean", self.expression, self.query, ensure_expr(value), default
        )


@dataclass(frozen=True, eq=False)
class GroupedAnyExpression(Expression):
    expression: Expression
    query: QueryProxy

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> bool:
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

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> Any:
        if self.query not in ctx:
            return self._empty_group_value()
        values, count = self._matching_values(ctx, world)
        return self._finish(values, count)

    def _matching_values(self, ctx: ExpressionContext, world: EcsWorld) -> tuple[list[Any], int]:
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
        return values, count

    def _empty_group_value(self) -> Any:
        if self.kind == "count":
            return 0
        if self.default is not None:
            return self.default
        if self.kind == "sum":
            return 0
        raise ValueError(f"Grouped {self.kind} aggregate is empty and no default was provided.")

    def _finish(self, values: list[Any], count: int) -> Any:
        if self.kind == "count":
            return count
        if self.kind == "sum":
            return sum(values) if values else 0
        if self.kind == "min":
            return self._min_or_default(values)
        if self.kind == "max":
            return self._max_or_default(values)
        if self.kind == "mean":
            return self._mean_or_default(values)
        raise ValueError(f"Unsupported grouped aggregate {self.kind!r}.")

    def _min_or_default(self, values: list[Any]) -> Any:
        if values:
            return min(values)
        if self.default is not None:
            return self.default
        raise ValueError("Grouped min aggregate is empty and no default was provided.")

    def _max_or_default(self, values: list[Any]) -> Any:
        if values:
            return max(values)
        if self.default is not None:
            return self.default
        raise ValueError("Grouped max aggregate is empty and no default was provided.")

    def _mean_or_default(self, values: list[Any]) -> Any:
        if values:
            return sum(values) / len(values)
        if self.default is not None:
            return self.default
        raise ValueError("Grouped mean aggregate is empty and no default was provided.")


@dataclass(frozen=True, eq=False)
class ExistsExpression(Expression):
    query: QueryProxy
    predicate: Expression

    def eval(self, ctx: ExpressionContext, world: EcsWorld) -> bool:
        for joined in world.iter_join_contexts_for(ctx, self.predicate, include_query=self.query):
            if bool(self.predicate.eval(joined, world)):
                return True
        return False


@dataclass(frozen=True)
class ExistsBuilder:
    query: QueryProxy

    def where(self, predicate: object) -> ExistsExpression:
        """Build a lazy boolean expression that checks for any matching row.

        Args:
            predicate: Value or expression evaluated for each candidate row.

        Returns:
            An expression that is true when at least one candidate matches.
        """

        return ExistsExpression(self.query, ensure_expr(predicate))


__all__ = [
    "ExistsBuilder",
    "ExistsExpression",
    "GroupedAnyExpression",
    "GroupedExpression",
    "GroupedValueAggregateExpression",
]
