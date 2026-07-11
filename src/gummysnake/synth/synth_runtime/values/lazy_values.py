from __future__ import annotations

import builtins
import random as _random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Self, SupportsIndex, cast, overload

from gummysnake.exceptions import ArgumentValidationError
from gummysnake.synth.synth_runtime.values.foundation import (
    EvalContext,
    Expression,
    SynthPlanError,
    _as_int,
    _current_repeat_depth_or_none,
    _next_expression_id,
)


@dataclass(frozen=True, slots=True, eq=False)
class MusicExpression(Expression):
    kind: Literal["chord", "scale", "octs"]
    root: Expression
    name: str | None = None
    count: Expression | None = None
    id: int = field(default_factory=_next_expression_id, repr=False, compare=False)
    repeat_depth: int | None = field(
        default_factory=_current_repeat_depth_or_none,
        repr=False,
        compare=False,
    )

    def evaluate(self, ctx: EvalContext) -> object:
        return _cached_expression_value(
            ctx,
            self.repeat_depth,
            self.id,
            lambda: self._evaluate_uncached(ctx),
        )

    def _evaluate_uncached(self, ctx: EvalContext) -> object:
        root = resolve_value(self.root, ctx)
        count = _as_int(resolve_value(self.count, ctx)) if self.count is not None else None
        if self.kind == "chord":
            from gummysnake.synth.synth_runtime.values.scales_and_specs import _chord_from_root

            return _chord_from_root(root, self.name or "major")
        if self.kind == "scale":
            from gummysnake.synth.synth_runtime.values.scales_and_specs import _scale_from_root

            return _scale_from_root(root, self.name or "major", count or 1)
        if self.kind == "octs":
            from gummysnake.synth.synth_runtime.values.scales_and_specs import _octaves_from_root

            return _octaves_from_root(root, count or 1)
        raise SynthPlanError(f"Unknown music expression kind: {self.kind}.")


@dataclass(frozen=True, slots=True, eq=False)
class SampleDurationExpression(Expression):
    sample_name: Expression
    opts: Mapping[str, object]
    id: int = field(default_factory=_next_expression_id, repr=False, compare=False)
    repeat_depth: int | None = field(
        default_factory=_current_repeat_depth_or_none,
        repr=False,
        compare=False,
    )

    def evaluate(self, ctx: EvalContext) -> object:
        return _cached_expression_value(
            ctx,
            self.repeat_depth,
            self.id,
            lambda: self._evaluate_uncached(ctx),
        )

    def _evaluate_uncached(self, ctx: EvalContext) -> object:
        sample_name = resolve_value(self.sample_name, ctx)
        opts = {name: resolve_value(value, ctx) for name, value in self.opts.items()}
        from gummysnake.synth.synth_runtime.playback_export.samples_and_export import (
            _sample_duration_seconds,
        )

        return _sample_duration_seconds(sample_name, opts)


@dataclass(frozen=True, slots=True, eq=False)
class TickExpression(Expression):
    values: Expression | None = None
    name: str = "default"
    advance: bool = True
    id: int = field(default_factory=_next_expression_id, repr=False, compare=False)
    repeat_depth: int | None = field(
        default_factory=_current_repeat_depth_or_none,
        repr=False,
        compare=False,
    )

    def evaluate(self, ctx: EvalContext) -> object:
        return _cached_expression_value(
            ctx,
            self.repeat_depth,
            self.id,
            lambda: self._evaluate_uncached(ctx),
        )

    def _evaluate_uncached(self, ctx: EvalContext) -> object:
        index = ctx.ticks.get(self.name, -1)
        if self.advance:
            index += 1
            ctx.ticks[self.name] = index
        if self.values is None:
            return index
        source = resolve_value(self.values, ctx)
        if not isinstance(source, Sequence) or isinstance(source, str | bytes | bytearray):
            raise ArgumentValidationError("tick/look values must be a sequence or ring.")
        if not source:
            raise ArgumentValidationError("tick/look cannot index an empty sequence.")
        return resolve_value(source[index % len(source)], ctx)


def ensure_expr(value: object) -> Expression:
    """Convert a Python value into a lazy synth expression."""

    if isinstance(value, Expression):
        return value
    from gummysnake.synth.synth_runtime.values.expressions import LiteralExpression

    return LiteralExpression(value)


def _cached_expression_value(
    ctx: EvalContext,
    repeat_depth: int | None,
    expression_id: int,
    compute: Callable[[], object],
) -> object:
    key = _expression_binding_key(ctx, repeat_depth, expression_id)
    if key is None:
        return compute()
    if key not in ctx.bindings:
        ctx.bindings[key] = compute()
    return ctx.bindings[key]


def _expression_binding_key(
    ctx: EvalContext,
    repeat_depth: int | None,
    expression_id: int,
) -> tuple[str, tuple[object, ...], int] | None:
    if repeat_depth is None:
        return None
    return ("expr", ctx.repeat_scope[:repeat_depth], expression_id)


def _source_bind_key(
    ctx: EvalContext,
    repeat_depth: int,
    bind_id: int,
) -> tuple[str, tuple[object, ...], int]:
    return ("source_bind", ctx.repeat_scope[:repeat_depth], bind_id)


def _source_bound_expression(expression: Expression) -> Expression:
    from gummysnake.synth.synth_runtime.composition.builder_context import _CURRENT_BUILDER

    builder = _CURRENT_BUILDER.get()
    if builder is None:
        return expression
    return builder.add_bind(expression)


def _expression_repeat_depth(expression: Expression, default: int) -> int:
    repeat_depth = getattr(expression, "repeat_depth", None)
    return default if repeat_depth is None else int(repeat_depth)


def resolve_value(value: object, ctx: EvalContext) -> object:
    """Evaluate lazy values recursively."""

    if isinstance(value, Expression):
        return value.evaluate(ctx)
    if isinstance(value, Ring):
        return Ring(resolve_value(item, ctx) for item in value)
    if isinstance(value, list):
        return [resolve_value(item, ctx) for item in value]
    if isinstance(value, tuple):
        return tuple(resolve_value(item, ctx) for item in value)
    if isinstance(value, dict):
        return {key: resolve_value(item, ctx) for key, item in value.items()}
    return value


class Ring(tuple[object, ...]):
    """Immutable Sonic Pi-style ring with wrapping indexes and chain helpers."""

    def __new__(cls, values: Iterable[object] = ()) -> Self:
        return super().__new__(cls, tuple(values))

    @overload
    def __getitem__(self, index: SupportsIndex) -> object: ...

    @overload
    def __getitem__(self, index: slice) -> Ring: ...

    def __getitem__(self, index: SupportsIndex | slice) -> object:
        if isinstance(index, slice):
            return Ring(tuple(self)[index])
        if not self:
            raise IndexError("Cannot index an empty Ring.")
        position = index.__index__()
        return tuple(self)[position % len(self)]

    def choose(self) -> Expression:
        """Choose a random item from this ring at render time."""

        from gummysnake.synth.synth_runtime.values.pattern_helpers import choose

        return choose(self)

    def tick(self, name: str | None = None) -> Expression:
        """Advance and read this ring with a named logical tick counter."""

        return TickExpression(ensure_expr(self), name or "default", True)

    def look(self, name: str | None = None) -> Expression:
        """Read this ring at the current named tick counter without advancing it."""

        return TickExpression(ensure_expr(self), name or "default", False)

    def reverse(self) -> Ring:
        return Ring(reversed(tuple(self)))

    def sort(self) -> Ring:
        return Ring(sorted(tuple(self), key=repr))

    def shuffle(self, *, seed: int | None = None) -> Ring:
        values = list(self)
        rng = _random.Random(seed) if seed is not None else _random.Random(0)
        rng.shuffle(values)
        return Ring(values)

    def pick(self, count: int | None = None) -> Ring:
        size = len(self) if count is None else max(0, int(count))
        rng = _random.Random(0)
        return Ring(self[rng.randrange(len(self))] for _ in builtins.range(size))

    def take(self, count: int) -> Ring:
        return Ring(tuple(self)[: max(0, int(count))])

    def drop(self, count: int) -> Ring:
        return Ring(tuple(self)[max(0, int(count)) :])

    def butlast(self) -> Ring:
        return Ring(tuple(self)[:-1])

    def drop_last(self, count: int) -> Ring:
        amount = max(0, int(count))
        return Ring(()) if amount >= len(self) else Ring(tuple(self)[:-amount])

    def take_last(self, count: int) -> Ring:
        amount = max(0, int(count))
        return Ring(tuple(self)[-amount:]) if amount else Ring(())

    def stretch(self, count: int) -> Ring:
        amount = max(0, int(count))
        return Ring(item for item in self for _ in builtins.range(amount))

    def repeat(self, count: int) -> Ring:
        amount = max(0, int(count))
        return Ring(tuple(self) * amount)

    def mirror(self) -> Ring:
        return Ring(tuple(self) + tuple(reversed(self)))

    def reflect(self) -> Ring:
        if len(self) <= 1:
            return Ring(self)
        return Ring(tuple(self) + tuple(reversed(tuple(self)[1:-1])))

    def scale(self, factor: float) -> Ring:
        return Ring(cast(Any, item) * factor for item in self)


def ring(*values: object) -> Ring:
    """Create an immutable wrapping ring."""

    return Ring(values)
