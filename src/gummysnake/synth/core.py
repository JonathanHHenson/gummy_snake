"""Logical-track synth composition and deterministic audio rendering."""

from __future__ import annotations

import builtins
import contextlib
import functools
import importlib
import io
import json
import random as _random
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
import zlib
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self, SupportsIndex, cast, overload

from gummysnake.assets._audio_codec import MemorySoundSource
from gummysnake.assets.sound import Sound
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError, GummySnakeError

type Number = int | float
_SAMPLE_RATE = 44_100


def _builtin_sample_package_dir() -> Path:
    current_file = Path(__file__).resolve()
    parents = current_file.parents
    candidates = []
    if len(parents) > 3:
        candidates.append(parents[3] / "assets" / "samples" / "sonic_pi")
    if len(parents) > 2:
        candidates.append(parents[2] / "assets" / "samples" / "sonic_pi")
    if len(parents) > 1:
        candidates.append(parents[1] / "assets" / "samples" / "sonic_pi")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else current_file.parent / "assets" / "samples" / "sonic_pi"


_BUILTIN_SAMPLE_PACKAGE_DIR = _builtin_sample_package_dir()
_BUILTIN_SAMPLE_EXTENSIONS = (".flac", ".wav", ".aif", ".aiff", ".wave")
_PHYSICAL_PLAN_SCHEMA = "gummysnake.synth.physical_plan.v1"
_GSS_MAGIC = b"GSSPLAN\x01"
_GSS_HEADER = struct.Struct(">8sII")
_GSS_COMPRESSION = 1


def _asset_dir(*parts: str) -> Path:
    current_file = Path(__file__).resolve()
    parents = current_file.parents
    candidates = []
    if len(parents) > 3:
        candidates.append(parents[3].joinpath(*parts))
    if len(parents) > 2:
        candidates.append(parents[2].joinpath(*parts))
    if len(parents) > 1:
        candidates.append(parents[1].joinpath(*parts))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else current_file.parent.joinpath(*parts)


_BUILTIN_SYNTH_COMPILED_DIR = _asset_dir("assets", "synths", "compiled")
_BUILTIN_FX_COMPILED_DIR = _asset_dir("assets", "synths", "fx", "compiled")


def _as_float(value: object) -> float:
    return float(cast(Any, value))


def _as_int(value: object) -> int:
    return int(cast(Any, value))


class SynthPlanError(GummySnakeError):
    """Raised when synth logical-plan construction fails."""


class Format(StrEnum):
    """File formats supported by ``Track.save``."""

    WAV = "wav"
    MP3 = "mp3"
    GSS = "gss"
    GSFX = "gsfx"


@dataclass(frozen=True, slots=True)
class Duration:
    """Concrete render duration.

    Durations are stored in seconds because rendered media is wall-clock audio.
    Helpers such as :func:`duration` can still express values in beats using a
    BPM conversion.
    """

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds < 0:
            raise ArgumentValidationError("duration cannot be negative.")

    @property
    def beats(self) -> float:
        """Duration in beats at the default 60 BPM."""

        return self.seconds

    def __float__(self) -> float:
        return self.seconds


def duration(
    *,
    hours: float = 0.0,
    mins: float = 0.0,
    secs: float = 0.0,
    beats: float = 0.0,
    bpm: float = 60.0,
) -> Duration:
    """Create a render duration from clock units and/or beats.

    Args:
        hours: Hours to include.
        mins: Minutes to include.
        secs: Seconds to include.
        beats: Beat count to convert using ``bpm``.
        bpm: Tempo used for beat conversion.

    Returns:
        A concrete :class:`Duration`.
    """

    if bpm <= 0:
        raise ArgumentValidationError("duration bpm must be positive.")
    total = hours * 3600.0 + mins * 60.0 + secs + beats * 60.0 / bpm
    return Duration(float(total))


_EXPRESSION_COUNTER = 0


def _next_expression_id() -> int:
    global _EXPRESSION_COUNTER
    _EXPRESSION_COUNTER += 1
    return _EXPRESSION_COUNTER


def _current_repeat_depth_or_none() -> int | None:
    try:
        builder = _CURRENT_BUILDER.get()
    except NameError:
        return None
    if builder is None:
        return None
    return builder.repeat_depth


@dataclass(slots=True)
class EvalContext:
    """State used when evaluating logical expressions."""

    rng: _random.Random
    ticks: dict[str, int] = field(default_factory=dict)
    scope: tuple[object, ...] = ()
    repeat_scope: tuple[object, ...] = ()
    bindings: dict[tuple[str, tuple[object, ...], int], object] = field(default_factory=dict)


class Expression:
    """Base class for lazily evaluated synth-plan values."""

    def evaluate(self, ctx: EvalContext) -> object:
        raise NotImplementedError

    def __bool__(self) -> bool:
        raise SynthPlanError(
            "Synth expressions are lazy and cannot be used as Python booleans. "
            "Use .when(expr), sy.when(...), or arithmetic/comparison expressions."
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

    def __mod__(self, other: object) -> Expression:
        return BinaryExpression("mod", self, ensure_expr(other))

    def __rmod__(self, other: object) -> Expression:
        return BinaryExpression("mod", ensure_expr(other), self)

    def __pow__(self, other: object) -> Expression:
        return BinaryExpression("pow", self, ensure_expr(other))

    def __rpow__(self, other: object) -> Expression:
        return BinaryExpression("pow", ensure_expr(other), self)

    def __neg__(self) -> Expression:
        return UnaryExpression("neg", self)

    def __lt__(self, other: object) -> Expression:
        return CompareExpression("lt", self, ensure_expr(other))

    def __le__(self, other: object) -> Expression:
        return CompareExpression("le", self, ensure_expr(other))

    def __gt__(self, other: object) -> Expression:
        return CompareExpression("gt", self, ensure_expr(other))

    def __ge__(self, other: object) -> Expression:
        return CompareExpression("ge", self, ensure_expr(other))

    def __eq__(self, other: object) -> Expression:  # type: ignore[override]
        return CompareExpression("eq", self, ensure_expr(other))

    def __ne__(self, other: object) -> Expression:  # type: ignore[override]
        return CompareExpression("ne", self, ensure_expr(other))


@dataclass(frozen=True, slots=True, eq=False)
class LiteralExpression(Expression):
    value: object
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
            lambda: resolve_value(self.value, ctx),
        )


@dataclass(frozen=True, slots=True, eq=False)
class UnaryExpression(Expression):
    op: str
    operand: Expression
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
        value = resolve_value(self.operand, ctx)
        if self.op == "neg":
            return -cast(Number, value)
        raise SynthPlanError(f"Unknown unary synth expression op: {self.op}.")


@dataclass(frozen=True, slots=True, eq=False)
class BinaryExpression(Expression):
    op: str
    left: Expression
    right: Expression
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
        left = resolve_value(self.left, ctx)
        right = resolve_value(self.right, ctx)
        if self.op == "add":
            return cast(Any, left) + cast(Any, right)
        if self.op == "sub":
            return cast(Any, left) - cast(Any, right)
        if self.op == "mul":
            return cast(Any, left) * cast(Any, right)
        if self.op == "truediv":
            return cast(Any, left) / cast(Any, right)
        if self.op == "mod":
            return cast(Any, left) % cast(Any, right)
        if self.op == "pow":
            return cast(Any, left) ** cast(Any, right)
        raise SynthPlanError(f"Unknown binary synth expression op: {self.op}.")


@dataclass(frozen=True, slots=True, eq=False)
class CompareExpression(Expression):
    op: str
    left: Expression
    right: Expression
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
        left = resolve_value(self.left, ctx)
        right = resolve_value(self.right, ctx)
        if self.op == "lt":
            return cast(Any, left) < cast(Any, right)
        if self.op == "le":
            return cast(Any, left) <= cast(Any, right)
        if self.op == "gt":
            return cast(Any, left) > cast(Any, right)
        if self.op == "ge":
            return cast(Any, left) >= cast(Any, right)
        if self.op == "eq":
            return left == right
        if self.op == "ne":
            return left != right
        raise SynthPlanError(f"Unknown comparison synth expression op: {self.op}.")


@dataclass(frozen=True, slots=True, eq=False)
class RandomExpression(Expression):
    kind: Literal["rand", "rand_i", "rrand", "rrand_i", "dice", "one_in"]
    args: tuple[Expression, ...]
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
        values = tuple(resolve_value(arg, ctx) for arg in self.args)
        if self.kind == "rand":
            max_value = _as_float(values[0]) if values else 1.0
            return ctx.rng.random() * max_value
        if self.kind == "rand_i":
            max_value = _as_int(values[0]) if values else 2
            return ctx.rng.randrange(max(1, max_value))
        if self.kind == "rrand":
            low, high = (_as_float(values[0]), _as_float(values[1]))
            return ctx.rng.uniform(low, high)
        if self.kind == "rrand_i":
            low, high = (_as_int(values[0]), _as_int(values[1]))
            return ctx.rng.randint(low, high)
        if self.kind == "dice":
            sides = _as_int(values[0]) if values else 6
            if sides <= 0:
                raise ArgumentValidationError("dice sides must be positive.")
            return ctx.rng.randint(1, sides)
        if self.kind == "one_in":
            sides = _as_int(values[0])
            if sides <= 0:
                raise ArgumentValidationError("one_in probability denominator must be positive.")
            return ctx.rng.randrange(sides) == 0
        raise SynthPlanError(f"Unknown random synth expression kind: {self.kind}.")


@dataclass(frozen=True, slots=True, eq=False)
class ChoiceExpression(Expression):
    source: Expression
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
        source = resolve_value(self.source, ctx)
        if (
            isinstance(source, Ring)
            or isinstance(source, Sequence)
            and not isinstance(source, str | bytes | bytearray)
        ):
            values = tuple(source)
        else:
            raise ArgumentValidationError("choose() requires a non-empty sequence or ring.")
        if not values:
            raise ArgumentValidationError("choose() requires a non-empty sequence or ring.")
        return resolve_value(values[ctx.rng.randrange(len(values))], ctx)


@dataclass(frozen=True, slots=True, eq=False)
class BoundExpression(Expression):
    """Lazy value bound once for each expanded nested track call."""

    id: int
    call_id: int
    source: Expression

    def evaluate(self, ctx: EvalContext) -> object:
        key = ("bound", _call_scope_prefix(ctx.scope, self.call_id), self.id)
        if key not in ctx.bindings:
            ctx.bindings[key] = resolve_value(self.source, ctx)
        return ctx.bindings[key]


@dataclass(frozen=True, slots=True, eq=False)
class SourceBoundExpression(Expression):
    """Lazy value captured at its source position in a track plan."""

    id: int
    repeat_depth: int
    source: Expression

    def evaluate(self, ctx: EvalContext) -> object:
        key = _source_bind_key(ctx, self.repeat_depth, self.id)
        if key not in ctx.bindings:
            ctx.bindings[key] = resolve_value(self.source, ctx)
        return ctx.bindings[key]


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
            return _chord_from_root(root, self.name or "major")
        if self.kind == "scale":
            return _scale_from_root(root, self.name or "major", count or 1)
        if self.kind == "octs":
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
    try:
        builder = _CURRENT_BUILDER.get()
    except NameError:
        return expression
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


def range(start: float, stop: float | None = None, *, step: float = 1.0) -> Ring:  # noqa: A001
    """Create a numeric ring.

    This mirrors Sonic Pi's ``range`` constructor while keeping Python keyword
    style. ``stop`` is exclusive.
    """

    if stop is None:
        start, stop = 0.0, start
    if step == 0:
        raise ArgumentValidationError("range step cannot be zero.")
    values: list[float] = []
    current = float(start)
    end = float(stop)
    if step > 0:
        while current < end:
            values.append(current)
            current += step
    else:
        while current > end:
            values.append(current)
            current += step
    return Ring(values)


def line(start: float, stop: float, *, steps: int) -> Ring:
    """Create a ring of linearly interpolated values including both endpoints."""

    if steps <= 0:
        raise ArgumentValidationError("line steps must be positive.")
    if steps == 1:
        return Ring([float(start)])
    return Ring(start + (stop - start) * index / (steps - 1) for index in builtins.range(steps))


def bools(*values: int | bool) -> Ring:
    """Create a ring of booleans from truthy/falsy values."""

    return Ring(bool(value) for value in values)


def knit(*pairs: object) -> Ring:
    """Create a ring by repeating value/count pairs."""

    if len(pairs) % 2 != 0:
        raise ArgumentValidationError("knit() requires value/count pairs.")
    output: list[object] = []
    iterator = iter(pairs)
    for value, count in zip(iterator, iterator, strict=True):
        output.extend(value for _ in builtins.range(max(0, int(cast(Any, count)))))
    return Ring(output)


def spread(pulses: int, steps: int) -> Ring:
    """Create a Euclidean rhythm as a boolean ring."""

    if steps <= 0:
        raise ArgumentValidationError("spread steps must be positive.")
    pulses = max(0, min(int(pulses), int(steps)))
    return Ring(((index * pulses) % steps) < pulses for index in builtins.range(steps))


def octs(root: object, count: int) -> Ring | Expression:
    """Return octaves above ``root`` as MIDI note values."""

    if isinstance(root, Expression):
        return MusicExpression("octs", root, count=ensure_expr(count))
    return _octaves_from_root(root, count)


def tick(name: str | None = None) -> Expression:
    """Advance a named logical tick counter and return its index."""

    return TickExpression(None, name or "default", True)


def look(name: str | None = None) -> Expression:
    """Read a named logical tick counter without advancing it."""

    return TickExpression(None, name or "default", False)


def choose(values: object) -> Expression:
    """Choose a random value from a sequence at physical-plan/render time."""

    return _source_bound_expression(ChoiceExpression(ensure_expr(values)))


def rand(max_value: float = 1.0) -> Expression:
    """Return a lazy random float in ``[0, max_value)``."""

    return _source_bound_expression(RandomExpression("rand", (ensure_expr(max_value),)))


def rand_i(max_value: int) -> Expression:
    """Return a lazy random integer in ``[0, max_value)``."""

    return _source_bound_expression(RandomExpression("rand_i", (ensure_expr(max_value),)))


def rrand(low: float, high: float) -> Expression:
    """Return a lazy random float between two values."""

    return _source_bound_expression(
        RandomExpression("rrand", (ensure_expr(low), ensure_expr(high)))
    )


def rrand_i(low: int, high: int) -> Expression:
    """Return a lazy random integer between two inclusive bounds."""

    return _source_bound_expression(
        RandomExpression("rrand_i", (ensure_expr(low), ensure_expr(high)))
    )


def dice(sides: int = 6) -> Expression:
    """Return a lazy dice roll in ``1..sides``."""

    return _source_bound_expression(RandomExpression("dice", (ensure_expr(sides),)))


def one_in(sides: int) -> Expression:
    """Return a lazy boolean that is true with probability ``1 / sides``."""

    return _source_bound_expression(RandomExpression("one_in", (ensure_expr(sides),)))


_NOTE_OFFSETS = {
    "c": 0,
    "cs": 1,
    "c#": 1,
    "db": 1,
    "d": 2,
    "ds": 3,
    "d#": 3,
    "eb": 3,
    "e": 4,
    "f": 5,
    "fs": 6,
    "f#": 6,
    "gb": 6,
    "g": 7,
    "gs": 8,
    "g#": 8,
    "ab": 8,
    "a": 9,
    "as": 10,
    "a#": 10,
    "bb": 10,
    "b": 11,
}

_CHORD_INTERVALS = {
    "major": (0, 4, 7),
    "maj": (0, 4, 7),
    "M": (0, 4, 7),
    "minor": (0, 3, 7),
    "m": (0, 3, 7),
    "m7": (0, 3, 7, 10),
    "minor7": (0, 3, 7, 10),
    "maj7": (0, 4, 7, 11),
    "major7": (0, 4, 7, 11),
    "dom7": (0, 4, 7, 10),
    "7": (0, 4, 7, 10),
    "dim": (0, 3, 6),
    "dim7": (0, 3, 6, 9),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "m9": (0, 3, 7, 10, 14),
    "m13": (0, 3, 7, 10, 14, 17, 21),
}

_SCALE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "natural_minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor": (0, 2, 3, 5, 7, 9, 11),
    "major_pentatonic": (0, 2, 4, 7, 9),
    "minor_pentatonic": (0, 3, 5, 7, 10),
    "chromatic": tuple(builtins.range(12)),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
}


def note(value: object) -> float | None:
    """Convert a note name or MIDI-like number to a MIDI note value.

    ``None``, ``"r"``, and ``"rest"`` represent rests and return ``None``.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return None if not value else 60.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower().removeprefix(":")
        if text in {"r", "rest", "nil", "none", "false"}:
            return None
        if not text:
            raise ArgumentValidationError("Empty note name.")
        root = text[0]
        rest = text[1:]
        accidental = ""
        if rest.startswith(("#", "s", "b")):
            accidental = "#" if rest[0] in {"#", "s"} else "b"
            rest = rest[1:]
        name = root + accidental
        if name not in _NOTE_OFFSETS:
            raise ArgumentValidationError(f"Unsupported note name: {value!r}.")
        octave = int(rest) if rest else 4
        return float((octave + 1) * 12 + _NOTE_OFFSETS[name])
    raise ArgumentValidationError(f"Unsupported note value: {value!r}.")


def note_frequency(value: object) -> float:
    """Convert a note value to Hertz."""

    midi = note(value)
    if midi is None:
        return 0.0
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


@overload
def chord(root: Expression, name: str = "major") -> Expression: ...


@overload
def chord(root: str | int | float | None, name: str = "major") -> Ring: ...


def chord(root: object, name: str = "major") -> Ring | Expression:
    """Return a chord ring, or a lazy chord expression when ``root`` is lazy."""

    if isinstance(root, Expression):
        return MusicExpression("chord", root, name)
    return _chord_from_root(root, name)


@overload
def scale(root: Expression, name: str = "major", *, num_octaves: int = 1) -> Expression: ...


@overload
def scale(root: str | int | float | None, name: str = "major", *, num_octaves: int = 1) -> Ring: ...


def scale(root: object, name: str = "major", *, num_octaves: int = 1) -> Ring | Expression:
    """Return a scale ring, or a lazy scale expression when ``root`` is lazy."""

    if isinstance(root, Expression):
        return MusicExpression("scale", root, name, ensure_expr(num_octaves))
    return _scale_from_root(root, name, num_octaves)


def _chord_from_root(root: object, name: str) -> Ring:
    base = note(root)
    if base is None:
        return Ring(())
    intervals = _CHORD_INTERVALS.get(name, _CHORD_INTERVALS.get(name.lower()))
    if intervals is None:
        raise ArgumentValidationError(f"Unsupported chord name: {name!r}.")
    return Ring(base + interval for interval in intervals)


def _scale_from_root(root: object, name: str, num_octaves: int = 1) -> Ring:
    base = note(root)
    if base is None:
        return Ring(())
    intervals = _SCALE_INTERVALS.get(name, _SCALE_INTERVALS.get(name.lower()))
    if intervals is None:
        raise ArgumentValidationError(f"Unsupported scale name: {name!r}.")
    values: list[float] = []
    for octave_index in builtins.range(max(1, int(num_octaves))):
        values.extend(base + octave_index * 12 + interval for interval in intervals)
    return Ring(values)


def _octaves_from_root(root: object, count: int) -> Ring:
    base = note(root)
    if base is None:
        return Ring(())
    return Ring(base + index * 12 for index in builtins.range(max(0, int(count))))


@dataclass(frozen=True, slots=True)
class SynthSpec:
    name: str
    opts: Mapping[str, object] = field(default_factory=dict)


_DEFAULT_SYNTH_INPUT_NOTE = 60
_DEFAULT_SYNTH_LAYER_AMP = 1.0


@dataclass(frozen=True, slots=True)
class SynthLayer:
    wave: str
    transpose: object = 0.0
    amp: object = 1.0
    opts: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SynthSample:
    value: object
    filters: tuple[object, ...] = ()
    opts: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SynthSilence:
    opts: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SynthSignal:
    """Immutable source-synth signal plan used by ``@sy.synth`` definitions.

    ``SynthSignal`` gives source-defined synths a plan-building surface similar
    to tracks and ECS systems: start with :func:`synth_input`, append layers or
    sample/silence nodes with fluent methods, then call :meth:`output` to record
    primitive synth actions into the active plan. Multi-layer oscillator signals
    are emitted as one generic ``_layered`` primitive so envelopes, filters,
    slides, FX, and realtime scheduling stay shared across the oscillator bank.
    """

    note: object = _DEFAULT_SYNTH_INPUT_NOTE
    opts: Mapping[str, object] = field(default_factory=dict)
    layers: tuple[SynthLayer, ...] = ()
    samples: tuple[SynthSample, ...] = ()
    silences: tuple[SynthSilence, ...] = ()

    def layer(
        self,
        wave: str,
        *,
        transpose: object = 0.0,
        amp: object = 1.0,
        **opts: object,
    ) -> SynthSignal:
        """Append a primitive oscillator layer to this source synth."""

        layer = SynthLayer(str(wave).removeprefix("_"), transpose, amp, dict(opts))
        return SynthSignal(
            self.note,
            self.opts,
            (*self.layers, layer),
            self.samples,
            self.silences,
        )

    def sample(self, value: object, *filters: object, **opts: object) -> SynthSignal:
        """Append a sample trigger to this source synth."""

        sample_node = SynthSample(value, tuple(filters), dict(opts))
        return SynthSignal(
            self.note,
            self.opts,
            self.layers,
            (*self.samples, sample_node),
            self.silences,
        )

    def silence(self, **opts: object) -> SynthSignal:
        """Append an explicit silent primitive output.

        This is useful for source definitions that represent live input, mixers,
        or routing synths that have no offline signal in Gummy Snake yet.
        """

        silence_node = SynthSilence(dict(opts))
        return SynthSignal(
            self.note,
            self.opts,
            self.layers,
            self.samples,
            (*self.silences, silence_node),
        )

    def output(self) -> tuple[NodeHandle, ...]:
        """Record this source-synth signal into the active synth plan."""

        return synth_output(self)


_SYNTH_DEFINITIONS: dict[str, SynthDefinition] = {}
_SYNTH_EXPANSION_STACK: ContextVar[tuple[str, ...]] = ContextVar(
    "gummysnake_synth_expansion_stack", default=()
)
_FX_DEFINITIONS: dict[str, FxDefinition] = {}
_FX_EXPANSION_STACK: ContextVar[tuple[str, ...]] = ContextVar(
    "gummysnake_fx_expansion_stack", default=()
)
_FX_DEFINITION_CAPTURE: ContextVar[list[FxHandle] | None] = ContextVar(
    "gummysnake_fx_definition_capture", default=None
)


@dataclass(slots=True)
class FxHandle:
    """Handle for an FX context that can be controlled later in a track."""

    id: int
    name: str
    opts: dict[str, object]


@dataclass(frozen=True, slots=True)
class FxSignal:
    """Immutable source-FX signal plan used by ``@sy.fx`` definitions.

    The methods append generic low-level FX operations to the signal path. Calling
    :func:`fx_output` records the signal path as an FX plan node that the Rust
    renderer can execute without hard-coding public Sonic Pi FX names.
    """

    ops: tuple[Mapping[str, object], ...] = ()

    def _then(self, op_name: str, **opts: object) -> FxSignal:
        return FxSignal((*self.ops, {"op": op_name, **opts}))

    def level(self) -> FxSignal:
        return self._then("level")

    def decimator(self, **opts: object) -> FxSignal:
        return self._then("decimator", **opts)

    def krush_shape(self, **opts: object) -> FxSignal:
        return self._then("krush_shape", **opts)

    def distortion_shape(self, **opts: object) -> FxSignal:
        return self._then("distortion_shape", **opts)

    def tanh_shape(self, **opts: object) -> FxSignal:
        return self._then("tanh_shape", **opts)

    def filter(self, **opts: object) -> FxSignal:
        return self._then("filter", **opts)

    def bandpass(self, **opts: object) -> FxSignal:
        return self._then("bandpass", **opts)

    def band_eq(self, **opts: object) -> FxSignal:
        return self._then("band_eq", **opts)

    def normalise(self, **opts: object) -> FxSignal:
        return self._then("normalise", **opts)

    def normalize(self, **opts: object) -> FxSignal:
        return self.normalise(**opts)

    def pan(self, **opts: object) -> FxSignal:
        return self._then("pan", **opts)

    def reverb(self, **opts: object) -> FxSignal:
        return self._then("reverb", **opts)

    def gverb(self, **opts: object) -> FxSignal:
        return self._then("gverb", **opts)

    def echo(self, **opts: object) -> FxSignal:
        return self._then("echo", **opts)

    def slicer(self, **opts: object) -> FxSignal:
        return self._then("slicer", **opts)

    def panslicer(self, **opts: object) -> FxSignal:
        return self._then("panslicer", **opts)

    def wobble(self, **opts: object) -> FxSignal:
        return self._then("wobble", **opts)

    def ixi_techno(self, **opts: object) -> FxSignal:
        return self._then("ixi_techno", **opts)

    def compressor(self, **opts: object) -> FxSignal:
        return self._then("compressor", **opts)

    def pitch_shift(self, **opts: object) -> FxSignal:
        return self._then("pitch_shift", **opts)

    def whammy(self, **opts: object) -> FxSignal:
        return self._then("whammy", **opts)

    def ring_mod(self, **opts: object) -> FxSignal:
        return self._then("ring_mod", **opts)

    def octaver(self, **opts: object) -> FxSignal:
        return self._then("octaver", **opts)

    def vowel(self, **opts: object) -> FxSignal:
        return self._then("vowel", **opts)

    def flanger(self, **opts: object) -> FxSignal:
        return self._then("flanger", **opts)


@dataclass(slots=True)
class EventNode:
    id: int
    kind: Literal["play", "sample"]
    value: object
    opts: dict[str, object]
    beat: float
    synth_name: str
    synth_opts: dict[str, object]
    fx_chain: tuple[FxHandle, ...]
    condition: object | None = None
    control_note_transpose: object = 0.0


@dataclass(slots=True)
class SleepNode:
    beat: float
    duration_beats: object


@dataclass(slots=True)
class ControlNode:
    target_id: int
    opts: dict[str, object]
    beat: float
    target_scope_suffix: tuple[object, ...] = ()
    condition: object | None = None


@dataclass(slots=True)
class BindNode:
    id: int
    source: Expression
    repeat_depth: int
    beat: float


@dataclass(frozen=True, slots=True)
class ControlTarget:
    target_id: int
    scope_suffix: tuple[object, ...] = ()
    note_transpose: object = 0.0


@dataclass(slots=True)
class LoopNode:
    id: int
    body: tuple[PlanNode, ...]
    beat: float
    body_beats: float
    times: int | None = None


@dataclass(slots=True)
class ThreadNode:
    id: int
    body: tuple[PlanNode, ...]
    beat: float
    body_beats: float
    name: str | None = None


@dataclass(slots=True)
class CallNode:
    id: int
    name: str
    body: tuple[PlanNode, ...]
    beat: float
    body_beats: float


type PlanNode = EventNode | SleepNode | ControlNode | BindNode | LoopNode | ThreadNode | CallNode


@dataclass(frozen=True, slots=True)
class NodeHandle:
    """Handle returned by ``play``/``sample`` for conditional and control APIs."""

    node: EventNode
    scope_suffix: tuple[object, ...] = ()
    condition_nodes: tuple[EventNode, ...] = ()
    control_targets: tuple[ControlTarget, ...] = ()

    @property
    def id(self) -> int:
        return self.node.id

    def when(self, condition: object) -> NodeHandle:
        """Attach a lazy condition to this event."""

        targets = self.condition_nodes or (self.node,)
        for node in targets:
            node.condition = condition
        return self


@dataclass(frozen=True, slots=True)
class TrackPlan:
    """Logical plan captured from a ``@track`` function."""

    name: str
    nodes: tuple[PlanNode, ...]
    duration_beats: float
    loop: bool = False
    loop_times: int | None = None
    bpm: float = 60.0
    seed: int = 0

    def explain(self) -> str:
        """Return a human-readable logical-plan summary."""

        lines = [
            f"track {self.name!r} bpm={self.bpm:g} loop={self.loop} loop_times={self.loop_times}",
        ]
        _append_node_explain(lines, self.nodes, indent="  ")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ScheduledEvent:
    """Concrete sound trigger in a physical plan."""

    instance: tuple[object, ...]
    node_id: int
    kind: Literal["play", "sample"]
    time_seconds: float
    value: object
    opts: Mapping[str, object]
    synth_name: str
    synth_opts: Mapping[str, object]
    fx_chain: tuple[FxHandle, ...]


@dataclass(frozen=True, slots=True)
class ScheduledControl:
    """Concrete control change in a physical plan."""

    target_instance: tuple[object, ...]
    target_id: int
    time_seconds: float
    opts: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PhysicalPlan:
    """Expanded track ready for deterministic rendering."""

    events: tuple[ScheduledEvent, ...]
    controls: tuple[ScheduledControl, ...]
    duration_seconds: float
    sample_rate: int = _SAMPLE_RATE

    def explain(self) -> str:
        """Return a compact physical-plan summary."""

        return (
            f"PhysicalPlan(events={len(self.events)}, controls={len(self.controls)}, "
            f"duration_seconds={self.duration_seconds:.3f}, sample_rate={self.sample_rate})"
        )

    def to_dict(self, *, metadata: Mapping[str, object] | None = None) -> dict[str, object]:
        """Serialize this physical plan to a JSON-compatible dictionary.

        The format stores concrete scheduled events and controls, not lazy
        expressions. It is therefore suitable for compiled synth assets and can be
        loaded back with :meth:`from_dict` without executing the original Python
        source track.
        """

        payload: dict[str, object] = {
            "schema": _PHYSICAL_PLAN_SCHEMA,
            "duration_seconds": self.duration_seconds,
            "sample_rate": self.sample_rate,
            "events": [_scheduled_event_to_dict(event) for event in self.events],
            "controls": [_scheduled_control_to_dict(control) for control in self.controls],
        }
        if metadata is not None:
            payload["metadata"] = _serialize_synth_value(dict(metadata))
        return payload

    def to_bytes(self, *, metadata: Mapping[str, object] | None = None) -> bytes:
        """Serialize this physical plan to the binary Gummy Snake Synth container."""

        raw = json.dumps(
            self.to_dict(metadata=metadata),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        compressed = zlib.compress(raw, level=9)
        return _GSS_HEADER.pack(_GSS_MAGIC, _GSS_COMPRESSION, len(raw)) + compressed

    def save(self, path: str | Path, *, metadata: Mapping[str, object] | None = None) -> Path:
        """Write this physical plan to a binary plan file and return the path."""

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self.to_bytes(metadata=metadata))
        return output_path

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> PhysicalPlan:
        """Load a physical plan from :meth:`to_dict` output."""

        schema = payload.get("schema")
        if schema != _PHYSICAL_PLAN_SCHEMA:
            raise ArgumentValidationError(
                "Unsupported synth physical-plan schema "
                f"{schema!r}; expected {_PHYSICAL_PLAN_SCHEMA!r}."
            )
        events_value = payload.get("events", ())
        controls_value = payload.get("controls", ())
        if not isinstance(events_value, Sequence) or isinstance(events_value, str | bytes):
            raise ArgumentValidationError("Serialized synth physical plan events must be a list.")
        if not isinstance(controls_value, Sequence) or isinstance(controls_value, str | bytes):
            raise ArgumentValidationError("Serialized synth physical plan controls must be a list.")
        return cls(
            tuple(_scheduled_event_from_dict(event) for event in events_value),
            tuple(_scheduled_control_from_dict(control) for control in controls_value),
            _as_float(payload.get("duration_seconds", 0.0)),
            _as_int(payload.get("sample_rate", _SAMPLE_RATE)),
        )

    @classmethod
    def from_bytes(cls, payload: bytes | bytearray | memoryview) -> PhysicalPlan:
        """Load a physical plan from binary plan bytes."""

        data = bytes(payload)
        if len(data) < _GSS_HEADER.size:
            raise ArgumentValidationError("Serialized synth physical plan is too short.")
        magic, compression, raw_size = _GSS_HEADER.unpack(data[: _GSS_HEADER.size])
        if magic != _GSS_MAGIC:
            raise ArgumentValidationError(
                "Serialized synth physical plan has an invalid binary header."
            )
        body = data[_GSS_HEADER.size :]
        if compression == _GSS_COMPRESSION:
            raw = zlib.decompress(body)
        else:
            raise ArgumentValidationError(
                f"Unsupported synth physical-plan compression mode {compression}."
            )
        if len(raw) != raw_size:
            raise ArgumentValidationError("Serialized synth physical plan size check failed.")
        decoded = json.loads(raw.decode("utf-8"))
        if not isinstance(decoded, Mapping):
            raise ArgumentValidationError(
                "Serialized synth physical plan payload must contain an object."
            )
        return cls.from_dict(cast(Mapping[str, object], decoded))

    @classmethod
    def load(cls, path: str | Path) -> PhysicalPlan:
        """Load a physical plan from a binary plan file."""

        return cls.from_bytes(Path(path).read_bytes())

    def render(self, *, sample_rate: int | None = None) -> bytes:
        """Render this already-expanded plan to stereo 16-bit PCM WAV bytes."""

        return _render_physical_plan(
            self, sample_rate=self.sample_rate if sample_rate is None else sample_rate
        )


class PlanBuilder:
    """Mutable logical-plan builder used while a track function executes."""

    def __init__(self, *, bpm: float = 60.0, seed: int = 0, repeat_depth: int = 1) -> None:
        if bpm <= 0:
            raise ArgumentValidationError("Track BPM must be positive.")
        self.nodes: list[PlanNode] = []
        self.current_beat = 0.0
        self.bpm = float(bpm)
        self.seed = int(seed)
        self.repeat_depth = int(repeat_depth)
        self.synth_stack: list[SynthSpec] = [SynthSpec("beep", {})]
        self.fx_stack: list[FxHandle] = []

    def child(self, *, repeat_depth: int | None = None) -> PlanBuilder:
        child = PlanBuilder(
            bpm=self.bpm,
            seed=self.seed,
            repeat_depth=self.repeat_depth if repeat_depth is None else repeat_depth,
        )
        child.synth_stack = list(self.synth_stack)
        child.fx_stack = list(self.fx_stack)
        return child

    @property
    def current_synth(self) -> SynthSpec:
        return self.synth_stack[-1]

    def add_event(
        self, kind: Literal["play", "sample"], value: object, opts: dict[str, object]
    ) -> NodeHandle:
        synth_spec = self.current_synth
        if kind == "play":
            synth_definition = _lookup_synth_definition(synth_spec.name)
            if synth_definition is not None:
                return self.add_synth_definition_event(
                    synth_definition,
                    value,
                    {**dict(synth_spec.opts), **dict(opts)},
                )
        node = EventNode(
            id=_next_node_id(),
            kind=kind,
            value=value,
            opts=dict(opts),
            beat=self.current_beat,
            synth_name=synth_spec.name,
            synth_opts=dict(synth_spec.opts),
            fx_chain=self.expanded_fx_chain(),
        )
        self.nodes.append(node)
        return NodeHandle(node)

    def add_synth_definition_event(
        self,
        definition: SynthDefinition,
        value: object,
        opts: dict[str, object],
    ) -> NodeHandle:
        stack = _SYNTH_EXPANSION_STACK.get()
        if definition.name in stack:
            raise SynthPlanError(f"Recursive synth definition expansion for {definition.name!r}.")
        child = self.child()
        token_builder = _CURRENT_BUILDER.set(child)
        token_stack = _SYNTH_EXPANSION_STACK.set((*stack, definition.name))
        try:
            result = definition.func(value, **opts)
        finally:
            _SYNTH_EXPANSION_STACK.reset(token_stack)
            _CURRENT_BUILDER.reset(token_builder)
        if result is not None:
            raise SynthPlanError("@sy.synth functions must build actions and return None.")
        node = ThreadNode(
            id=_next_node_id(),
            body=tuple(child.nodes),
            beat=self.current_beat,
            body_beats=child.current_beat,
            name=f"synth:{definition.name}",
        )
        self.nodes.append(node)
        event_paths = _event_node_paths(child.nodes)
        if event_paths:
            first_event, first_path = event_paths[0]
            control_targets = tuple(
                ControlTarget(
                    event_node.id,
                    (node.id, node.name or "thread", *path),
                    event_node.control_note_transpose,
                )
                for event_node, path in event_paths
            )
            return NodeHandle(
                first_event,
                scope_suffix=(node.id, node.name or "thread", *first_path),
                condition_nodes=tuple(event_node for event_node, _path in event_paths),
                control_targets=control_targets,
            )
        placeholder = EventNode(
            id=_next_node_id(),
            kind="play",
            value=None,
            opts={},
            beat=self.current_beat,
            synth_name="_silence",
            synth_opts={},
            fx_chain=(),
        )
        return NodeHandle(placeholder)

    def add_sleep(self, beats: object) -> None:
        numeric = _literal_float_or_none(beats)
        if numeric is not None and numeric < 0:
            raise ArgumentValidationError("sleep() duration cannot be negative.")
        self.nodes.append(SleepNode(self.current_beat, beats))
        if numeric is not None:
            self.current_beat += numeric
        else:
            # Lazy sleep durations are evaluated later during physical expansion.
            # The builder still needs a beat estimate so following nodes and loop
            # bodies have stable relative positions in the logical plan.
            self.current_beat += _estimated_beats(beats)

    def add_control(
        self, target_id: int, opts: dict[str, object], target_scope_suffix: tuple[object, ...] = ()
    ) -> None:
        self.nodes.append(
            ControlNode(
                target_id=target_id,
                opts=dict(opts),
                beat=self.current_beat,
                target_scope_suffix=target_scope_suffix,
            )
        )

    def add_bind(self, source: Expression) -> SourceBoundExpression:
        bind_id = _next_node_id()
        repeat_depth = _expression_repeat_depth(source, self.repeat_depth)
        self.nodes.append(BindNode(bind_id, source, repeat_depth, self.current_beat))
        return SourceBoundExpression(bind_id, repeat_depth, source)

    def push_synth(self, spec: SynthSpec) -> None:
        self.synth_stack.append(spec)

    def pop_synth(self, spec: SynthSpec) -> None:
        popped = self.synth_stack.pop()
        if popped is not spec:
            raise SynthPlanError("Synth context stack was corrupted.")

    def push_fx(self, handle: FxHandle) -> None:
        self.fx_stack.append(handle)

    def pop_fx(self, handle: FxHandle) -> None:
        popped = self.fx_stack.pop()
        if popped is not handle:
            raise SynthPlanError("FX context stack was corrupted.")

    def expanded_fx_chain(self) -> tuple[FxHandle, ...]:
        expanded: list[FxHandle] = []
        for handle in self.fx_stack:
            expanded.extend(_expand_fx_handle(handle))
        return tuple(expanded)


_CURRENT_BUILDER: ContextVar[PlanBuilder | None] = ContextVar(
    "gummysnake_synth_builder", default=None
)
_NODE_COUNTER = 0


def _next_node_id() -> int:
    global _NODE_COUNTER
    _NODE_COUNTER += 1
    return _NODE_COUNTER


def _current_builder() -> PlanBuilder:
    builder = _CURRENT_BUILDER.get()
    if builder is None:
        raise SynthPlanError("This synth API must be called while building a @sy.track plan.")
    return builder


def _call_scope_prefix(scope: tuple[object, ...], call_id: int) -> tuple[object, ...]:
    marker = ("call", call_id)
    for index in builtins.range(len(scope) - 1, -1, -1):
        if scope[index] == marker:
            return scope[: index + 1]
    return scope


@contextlib.contextmanager
def _eval_scope(
    ctx: EvalContext,
    scope: tuple[object, ...],
    repeat_scope: tuple[object, ...] | None = None,
) -> Iterator[None]:
    previous_scope = ctx.scope
    previous_repeat_scope = ctx.repeat_scope
    ctx.scope = scope
    if repeat_scope is not None:
        ctx.repeat_scope = repeat_scope
    try:
        yield
    finally:
        ctx.scope = previous_scope
        ctx.repeat_scope = previous_repeat_scope


def _literal_float_or_none(value: object) -> float | None:
    if isinstance(value, Expression):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _estimated_beats(value: object) -> float:
    """Best-effort build-time estimate for lazy sleep values."""

    if isinstance(value, SourceBoundExpression):
        return _estimated_beats(value.source)
    if isinstance(value, SampleDurationExpression) and (
        not isinstance(value.sample_name, Expression)
        or isinstance(value.sample_name, LiteralExpression)
    ):
        with contextlib.suppress(Exception):
            ctx = EvalContext(_random.Random(0))
            return max(0.0, _as_float(value.evaluate(ctx)))
    if isinstance(value, BinaryExpression):
        left = _estimated_beats(value.left)
        right = _estimated_beats(value.right)
        with contextlib.suppress(ZeroDivisionError):
            if value.op == "add":
                return max(0.0, left + right)
            if value.op == "sub":
                return max(0.0, left - right)
            if value.op == "mul":
                return max(0.0, left * right)
            if value.op == "truediv":
                return max(0.0, left / right)
    if isinstance(value, LiteralExpression):
        numeric = _literal_float_or_none(value.value)
        if numeric is not None:
            return max(0.0, numeric)
    if isinstance(value, ChoiceExpression):
        with contextlib.suppress(Exception):
            ctx = EvalContext(_random.Random(0))
            source = resolve_value(value.source, ctx)
            if isinstance(source, Sequence) and not isinstance(source, str | bytes | bytearray):
                numeric_values = [
                    _as_float(item) for item in source if isinstance(item, int | float)
                ]
                if numeric_values:
                    return sum(numeric_values) / len(numeric_values)
    if isinstance(value, TickExpression) and value.values is not None:
        with contextlib.suppress(Exception):
            ctx = EvalContext(_random.Random(0))
            source = resolve_value(value.values, ctx)
            if isinstance(source, Sequence) and not isinstance(source, str | bytes | bytearray):
                tick_values = [_as_float(item) for item in source if isinstance(item, int | float)]
                if tick_values:
                    return sum(tick_values) / len(tick_values)
    return 1.0


class SynthContext:
    """Context manager returned by :func:`synth`."""

    def __init__(self, name: str, opts: Mapping[str, object]) -> None:
        self._spec = SynthSpec(str(name), dict(opts))

    def __enter__(self) -> SynthContext:
        _current_builder().push_synth(self._spec)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _current_builder().pop_synth(self._spec)


class FxContext:
    """Context manager returned by :func:`fx`."""

    def __init__(self, name: str, opts: Mapping[str, object]) -> None:
        self.handle = FxHandle(id=_next_node_id(), name=str(name), opts=dict(opts))

    def __enter__(self) -> FxHandle:
        capture = _FX_DEFINITION_CAPTURE.get()
        if capture is not None:
            capture.append(self.handle)
        _current_builder().push_fx(self.handle)
        return self.handle

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _current_builder().pop_fx(self.handle)


class LoopContext:
    """Context manager that records a repeated logical block."""

    def __init__(self, *, times: int | None = None) -> None:
        if times is not None and times < 0:
            raise ArgumentValidationError("loop(times=...) cannot be negative.")
        self._times = times
        self._parent: PlanBuilder | None = None
        self._child: PlanBuilder | None = None
        self._token: object | None = None

    def __enter__(self) -> LoopContext:
        parent = _current_builder()
        child = parent.child(repeat_depth=parent.repeat_depth + 1)
        self._parent = parent
        self._child = child
        self._token = _CURRENT_BUILDER.set(child)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        assert self._parent is not None and self._child is not None and self._token is not None
        _CURRENT_BUILDER.reset(cast(Any, self._token))
        if exc_type is not None:
            return
        node = LoopNode(
            id=_next_node_id(),
            body=tuple(self._child.nodes),
            beat=self._parent.current_beat,
            body_beats=self._child.current_beat,
            times=self._times,
        )
        self._parent.nodes.append(node)
        if self._times is not None:
            self._parent.current_beat += self._child.current_beat * self._times
        else:
            self._parent.current_beat += self._child.current_beat


class ThreadContext:
    """Context manager that records a parallel logical branch."""

    def __init__(self, *, name: str | None = None) -> None:
        self._name = name
        self._parent: PlanBuilder | None = None
        self._child: PlanBuilder | None = None
        self._token: object | None = None

    def __enter__(self) -> ThreadContext:
        parent = _current_builder()
        child = parent.child()
        self._parent = parent
        self._child = child
        self._token = _CURRENT_BUILDER.set(child)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        assert self._parent is not None and self._child is not None and self._token is not None
        _CURRENT_BUILDER.reset(cast(Any, self._token))
        if exc_type is not None:
            return
        self._parent.nodes.append(
            ThreadNode(
                id=_next_node_id(),
                body=tuple(self._child.nodes),
                beat=self._parent.current_beat,
                body_beats=self._child.current_beat,
                name=self._name,
            )
        )


@overload
def synth(func: _SynthFunction, /) -> SynthDefinition: ...


@overload
def synth(name: str, /, **opts: object) -> SynthContext: ...


@overload
def synth(*, name: str | None = None) -> Callable[[_SynthFunction], SynthDefinition]: ...


def synth(
    name_or_func: str | _SynthFunction | None = None,
    /,
    **opts: object,
) -> SynthContext | SynthDefinition | Callable[[_SynthFunction], SynthDefinition]:
    """Select a synth context or decorate a source-defined synth.

    ``with sy.synth("tb303")`` keeps the existing context-manager behavior.
    ``@sy.synth`` or ``@sy.synth(name="tb303")`` registers a synth definition
    written in Gummy Snake source code.
    """

    decorator_name = opts.pop("name", None)
    if callable(name_or_func) and not isinstance(name_or_func, str):
        if decorator_name is not None and not isinstance(decorator_name, str):
            raise ArgumentValidationError("@sy.synth(name=...) must be a string.")
        return SynthDefinition(name_or_func, name=decorator_name)
    if name_or_func is None:
        if decorator_name is not None and not isinstance(decorator_name, str):
            raise ArgumentValidationError("@sy.synth(name=...) must be a string.")

        def decorate(inner: _SynthFunction) -> SynthDefinition:
            return SynthDefinition(inner, name=decorator_name)

        return decorate
    if decorator_name is not None:
        raise ArgumentValidationError("sy.synth('name', ...) cannot also pass name=....")
    return SynthContext(str(name_or_func), opts)


def use_synth(name: str, **opts: object) -> None:
    """Set the current synth for the remainder of the current builder scope."""

    builder = _current_builder()
    builder.synth_stack[-1] = SynthSpec(name, dict(opts))


def synth_input(value: object = _DEFAULT_SYNTH_INPUT_NOTE, **opts: object) -> SynthSignal:
    """Start a source-synth signal builder for an ``@sy.synth`` definition.

    Pass ``defaults={...}`` to supply source-defined option defaults before
    caller overrides. The returned :class:`SynthSignal` is immutable; each
    builder method returns a new signal value.
    """

    defaults = opts.pop("defaults", None)
    if defaults is not None and not isinstance(defaults, Mapping):
        raise ArgumentValidationError("synth_input(defaults=...) must be a mapping.")
    merged = dict(defaults or {})
    merged.update(opts)
    return SynthSignal(value, merged)


def synth_output(signal: SynthSignal) -> tuple[NodeHandle, ...]:
    """Record a source-synth signal into the active synth plan.

    Single layers become low-level primitive synth events (``_sine``, ``_saw``,
    etc.). Multi-layer oscillator banks become one generic ``_layered`` primitive
    carrying serializable layer metadata, so public Sonic Pi synth names still are
    not dispatched in Rust. Sample nodes become ordinary ``sy.sample`` events,
    and explicit silences use the ``_silence`` primitive.
    """

    handles: list[NodeHandle] = []
    base_opts = dict(signal.opts)
    base_amp = base_opts.pop("amp", _DEFAULT_SYNTH_LAYER_AMP)
    if len(signal.layers) == 1:
        layer_node = signal.layers[0]
        layer_opts = dict(base_opts)
        layer_opts.update(layer_node.opts)
        layer_opts["amp"] = _multiply_synth_amp(base_amp, layer_node.amp)
        with synth(f"_{layer_node.wave}"):
            handle = play(_transposed_synth_note(signal.note, layer_node.transpose), **layer_opts)
            handle.node.control_note_transpose = layer_node.transpose
            handles.append(handle)
    elif signal.layers:
        layer_opts = dict(base_opts)
        layer_opts["amp"] = base_amp
        layer_opts["layers"] = [_synth_layer_payload(layer_node) for layer_node in signal.layers]
        with synth("_layered"):
            handles.append(play(signal.note, **layer_opts))
    for sample_node in signal.samples:
        sample_opts = dict(sample_node.opts)
        sample_opts.update(signal.opts)
        handles.append(sample(sample_node.value, *sample_node.filters, **sample_opts))
    for silence_node in signal.silences:
        silence_opts = dict(silence_node.opts)
        silence_opts.update(signal.opts)
        with synth("_silence"):
            handles.append(play(signal.note, **silence_opts))
    return tuple(handles)


def _synth_layer_payload(layer_node: SynthLayer) -> dict[str, object]:
    return {
        "wave": layer_node.wave,
        "transpose": layer_node.transpose,
        "amp": layer_node.amp,
        "opts": dict(layer_node.opts),
    }


def _transposed_synth_note(value: object, transpose: object) -> object:
    if isinstance(transpose, int | float) and transpose == 0:
        return value
    if isinstance(value, Ring):
        return Ring(_transposed_synth_note(item, transpose) for item in value)
    if isinstance(value, list):
        return [_transposed_synth_note(item, transpose) for item in value]
    if isinstance(value, tuple):
        return tuple(_transposed_synth_note(item, transpose) for item in value)
    if isinstance(value, Expression):
        return value + transpose
    if isinstance(value, str | int | float | bool) or value is None:
        resolved = note(value)
        if resolved is None:
            return None
        if isinstance(transpose, Expression):
            return ensure_expr(resolved) + transpose
        if isinstance(transpose, int | float):
            return resolved + float(transpose)
    return value


def _multiply_synth_amp(base_amp: object, layer_amp: object) -> object:
    left = _synth_numeric_or_default(base_amp, _DEFAULT_SYNTH_LAYER_AMP)
    right = _synth_numeric_or_default(layer_amp, 1.0)
    if isinstance(left, Expression) or isinstance(right, Expression):
        return ensure_expr(left) * ensure_expr(right)
    return float(cast(Any, left)) * float(cast(Any, right))


def _synth_numeric_or_default(value: object, default: float) -> object:
    if isinstance(value, Expression):
        return value
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return default


@overload
def fx(func: _FxFunction, /) -> FxDefinition: ...


@overload
def fx(name: str, /, **opts: object) -> FxContext: ...


@overload
def fx(*, name: str | None = None) -> Callable[[_FxFunction], FxDefinition]: ...


def fx(
    name_or_func: str | _FxFunction | None = None,
    /,
    **opts: object,
) -> FxContext | FxDefinition | Callable[[_FxFunction], FxDefinition]:
    """Apply an FX context or decorate a source-defined FX.

    ``with sy.fx("reverb")`` keeps the existing context-manager behavior.
    ``@sy.fx`` or ``@sy.fx(name="reverb")`` registers an FX definition that
    composes lower-level FX contexts in Gummy Snake source.
    """

    decorator_name = opts.pop("name", None)
    if callable(name_or_func) and not isinstance(name_or_func, str):
        if decorator_name is not None and not isinstance(decorator_name, str):
            raise ArgumentValidationError("@sy.fx(name=...) must be a string.")
        return FxDefinition(name_or_func, name=decorator_name)
    if name_or_func is None:
        if decorator_name is not None and not isinstance(decorator_name, str):
            raise ArgumentValidationError("@sy.fx(name=...) must be a string.")

        def decorate(inner: _FxFunction) -> FxDefinition:
            return FxDefinition(inner, name=decorator_name)

        return decorate
    if decorator_name is not None:
        raise ArgumentValidationError("sy.fx('name', ...) cannot also pass name=....")
    return FxContext(str(name_or_func), opts)


def fx_input() -> FxSignal:
    """Return the source signal placeholder for an ``@sy.fx`` definition."""

    return FxSignal()


def fx_output(signal: FxSignal, **opts: object) -> FxHandle:
    """Record the output signal for an ``@sy.fx`` definition.

    The signal operations are serialized as a generic low-level FX chain. Public
    FX definitions should use this builder instead of assembling operation lists
    by hand.
    """

    ops = [dict(operation) for operation in signal.ops]
    if not ops:
        ops = [{"op": "level"}]
    context = FxContext("_chain", {"ops": ops, **opts})
    with context as handle:
        return handle


def loop(*, times: int | None = None) -> LoopContext:
    """Repeat a nested logical block.

    ``times=None`` records an open-ended loop. Rendering repeats it until the
    requested track duration is filled.
    """

    return LoopContext(times=times)


def thread(*, name: str | None = None) -> ThreadContext:
    """Record a nested logical block that starts in parallel with following code."""

    return ThreadContext(name=name)


def play(value: object, **opts: object) -> NodeHandle:
    """Trigger the current synth at the current logical beat."""

    return _current_builder().add_event("play", value, dict(opts))


def sample(value: object, *filters: object, **opts: object) -> NodeHandle:
    """Trigger a built-in, external, or generated sample at the current beat."""

    sample_value: object = value if not filters else (value, *filters)
    return _current_builder().add_event("sample", sample_value, dict(opts))


def sleep(beats: object) -> None:
    """Advance the current logical timeline by a number of beats."""

    _current_builder().add_sleep(beats)


def control(target: NodeHandle | FxHandle, **opts: object) -> None:
    """Control a running synth/sample/FX handle at the current logical beat."""

    builder = _current_builder()
    if isinstance(target, NodeHandle):
        control_targets = target.control_targets or (
            ControlTarget(target.id, target.scope_suffix, target.node.control_note_transpose),
        )
        for control_target in control_targets:
            builder.add_control(
                control_target.target_id,
                _control_opts_for_target(opts, control_target),
                control_target.scope_suffix,
            )
        return
    builder.add_control(target.id, dict(opts), ())


def _control_opts_for_target(
    opts: Mapping[str, object], control_target: ControlTarget
) -> dict[str, object]:
    target_opts = dict(opts)
    if "note" in target_opts:
        target_opts["note"] = _transposed_synth_note(
            target_opts["note"], control_target.note_transpose
        )
    return target_opts


def sample_duration(value: object, **opts: object) -> Expression:
    """Return a lazy sample duration in beats at the default 60 BPM."""

    return SampleDurationExpression(ensure_expr(value), dict(opts))


@functools.cache
def _builtin_sample_path(name: str) -> Path | None:
    normalized = name.strip().removeprefix(":")
    if not normalized:
        return None
    for extension in _BUILTIN_SAMPLE_EXTENSIONS:
        candidate = _BUILTIN_SAMPLE_PACKAGE_DIR / f"{normalized}{extension}"
        if candidate.exists():
            return candidate
    return None


def _resolve_sample_source(value: object) -> object:
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        sample_path = _builtin_sample_path(value)
        if sample_path is not None:
            return sample_path
    return value


def _event_node_paths(
    nodes: Sequence[PlanNode], prefix: tuple[object, ...] = ()
) -> tuple[tuple[EventNode, tuple[object, ...]], ...]:
    event_paths: list[tuple[EventNode, tuple[object, ...]]] = []
    for node in nodes:
        if isinstance(node, EventNode):
            event_paths.append((node, prefix))
        elif isinstance(node, ThreadNode):
            event_paths.extend(
                _event_node_paths(node.body, (*prefix, node.id, node.name or "thread"))
            )
        elif isinstance(node, CallNode):
            event_paths.extend(_event_node_paths(node.body, (*prefix, ("call", node.id))))
        elif isinstance(node, LoopNode):
            event_paths.extend(_event_node_paths(node.body, (*prefix, node.id, 0)))
    return tuple(event_paths)


def _synth_definition_key(name: str) -> str:
    return name.strip().removeprefix(":")


def _synth_definition_module_name(name: str) -> str:
    return _synth_definition_key(name).replace("-", "_")


def _fx_definition_key(name: str) -> str:
    return name.strip().removeprefix(":")


def _fx_definition_module_name(name: str) -> str:
    return _fx_definition_key(name).replace("-", "_")


def _lookup_synth_definition(name: str) -> SynthDefinition | None:
    key = _synth_definition_key(name)
    if key.startswith("_"):
        return None
    definition = _SYNTH_DEFINITIONS.get(key)
    if definition is not None:
        return definition
    with contextlib.suppress(ModuleNotFoundError):
        importlib.import_module(f"gummysnake.synth.builtins.{_synth_definition_module_name(key)}")
    return _SYNTH_DEFINITIONS.get(key)


def _lookup_fx_definition(name: str) -> FxDefinition | None:
    key = _fx_definition_key(name)
    if key.startswith("_"):
        return None
    definition = _FX_DEFINITIONS.get(key)
    if definition is not None:
        return definition
    with contextlib.suppress(ModuleNotFoundError):
        importlib.import_module(f"gummysnake.synth.fx_builtins.{_fx_definition_module_name(key)}")
    return _FX_DEFINITIONS.get(key)


def _expand_fx_handle(handle: FxHandle) -> tuple[FxHandle, ...]:
    definition = _lookup_fx_definition(handle.name)
    if definition is None:
        return (handle,)
    return definition.build_chain(handle.id, handle.opts)


def when(condition: object, event: NodeHandle | None = None) -> NodeHandle | Expression:
    """Attach or return a lazy condition.

    If ``event`` is supplied, this is equivalent to ``event.when(condition)``.
    Otherwise the condition expression is returned for use by callers that prefer
    named helper style.
    """

    if event is not None:
        return event.when(condition)
    return ensure_expr(condition)


def _bind_track_call_value(value: object, call_id: int) -> object:
    if isinstance(value, Expression):
        return BoundExpression(_next_node_id(), call_id, value)
    if isinstance(value, Ring):
        return Ring(_bind_track_call_value(item, call_id) for item in value)
    if isinstance(value, list):
        return [_bind_track_call_value(item, call_id) for item in value]
    if isinstance(value, tuple):
        return tuple(_bind_track_call_value(item, call_id) for item in value)
    if isinstance(value, dict):
        return {key: _bind_track_call_value(item, call_id) for key, item in value.items()}
    return value


type _TrackFunction = Callable[..., object]
type _SynthFunction = Callable[..., object]
type _FxFunction = Callable[..., object]


class SynthDefinition:
    """Callable wrapper produced by ``@sy.synth`` for source-defined synths."""

    def __init__(self, func: _SynthFunction, *, name: str | None = None) -> None:
        self.func = func
        function_name = str(getattr(func, "__name__", "synth"))
        self.name = _synth_definition_key(name or function_name)
        self.__name__ = function_name
        self.__doc__ = getattr(func, "__doc__", None)
        _SYNTH_DEFINITIONS[self.name] = self
        package = sys.modules.get("gummysnake.synth")
        if package is not None and not hasattr(package, self.name):
            setattr(package, self.name, self)

    def __call__(self, value: object = 60, **opts: object) -> Track:
        """Build this synth definition as a standalone source track."""

        return self.build(value, **opts)

    def build(self, value: object = 60, **opts: object) -> Track:
        builder = PlanBuilder(seed=0)
        token_builder = _CURRENT_BUILDER.set(builder)
        token_stack = _SYNTH_EXPANSION_STACK.set((self.name,))
        try:
            result = self.func(value, **opts)
        finally:
            _SYNTH_EXPANSION_STACK.reset(token_stack)
            _CURRENT_BUILDER.reset(token_builder)
        if result is not None:
            raise SynthPlanError("@sy.synth functions must build actions and return None.")
        plan = TrackPlan(
            self.name,
            tuple(builder.nodes),
            builder.current_beat,
            bpm=builder.bpm,
            seed=builder.seed,
        )
        return Track(self, plan)

    def physical_plan(
        self, duration: Duration | float | None = None, **opts: object
    ) -> PhysicalPlan:
        return self.build(**opts).physical_plan(duration)

    def save(
        self,
        path: str | Path,
        *,
        duration: Duration | float | None = None,
        sample_rate: int = _SAMPLE_RATE,
        **opts: object,
    ) -> Path:
        return self.build(**opts).save(path, duration=duration, sample_rate=sample_rate)


class FxDefinition:
    """Callable wrapper produced by ``@sy.fx`` for source-defined FX."""

    def __init__(self, func: _FxFunction, *, name: str | None = None) -> None:
        self.func = func
        function_name = str(getattr(func, "__name__", "fx"))
        self.name = _fx_definition_key(name or function_name)
        self.__name__ = function_name
        self.__doc__ = getattr(func, "__doc__", None)
        _FX_DEFINITIONS[self.name] = self
        package = sys.modules.get("gummysnake.synth")
        if package is not None and not hasattr(package, self.name):
            setattr(package, self.name, self)

    def __call__(self, **opts: object) -> FxContext:
        """Return an FX context using this source-defined FX name."""

        return FxContext(self.name, opts)

    def build_chain(self, source_id: int, opts: Mapping[str, object]) -> tuple[FxHandle, ...]:
        """Expand this source FX into lower-level FX handles for an event."""

        stack = _FX_EXPANSION_STACK.get()
        if self.name in stack:
            raise SynthPlanError(f"Recursive FX definition expansion for {self.name!r}.")
        child = PlanBuilder(seed=0)
        captured: list[FxHandle] = []
        token_builder = _CURRENT_BUILDER.set(child)
        token_stack = _FX_EXPANSION_STACK.set((*stack, self.name))
        token_capture = _FX_DEFINITION_CAPTURE.set(captured)
        try:
            result = self.func(**dict(opts))
        finally:
            _FX_DEFINITION_CAPTURE.reset(token_capture)
            _FX_EXPANSION_STACK.reset(token_stack)
            _CURRENT_BUILDER.reset(token_builder)
        if result is not None:
            raise SynthPlanError("@sy.fx functions must build FX contexts and return None.")
        expanded: list[FxHandle] = []
        for child_handle in captured:
            expanded.extend(
                _expand_fx_handle(FxHandle(source_id, child_handle.name, dict(child_handle.opts)))
            )
        return tuple(expanded)

    def build(self, **opts: object) -> Track:
        """Build this FX definition as a standalone source track for asset compilation."""

        builder = PlanBuilder(seed=0)
        token_builder = _CURRENT_BUILDER.set(builder)
        try:
            with FxContext(self.name, opts):
                with SynthContext("_saw", {}):
                    play(60, release=0.08, amp=0.35)
                sleep(0.08)
        finally:
            _CURRENT_BUILDER.reset(token_builder)
        plan = TrackPlan(
            self.name,
            tuple(builder.nodes),
            builder.current_beat,
            bpm=builder.bpm,
            seed=builder.seed,
        )
        return Track(self, plan)

    def physical_plan(
        self, duration: Duration | float | None = None, **opts: object
    ) -> PhysicalPlan:
        return self.build(**opts).physical_plan(duration)

    def save(
        self,
        path: str | Path,
        *,
        duration: Duration | float | None = None,
        sample_rate: int = _SAMPLE_RATE,
        **opts: object,
    ) -> Path:
        return self.build(**opts).save(path, duration=duration, sample_rate=sample_rate)


class TrackDefinition:
    """Callable wrapper produced by :func:`track`."""

    def __init__(
        self,
        func: _TrackFunction,
        *,
        loop: bool = False,
        loop_times: int | None = None,
        bpm: float = 60.0,
        seed: int = 0,
    ) -> None:
        if loop_times is not None and loop_times < 0:
            raise ArgumentValidationError("track(loop_times=...) cannot be negative.")
        self.func = func
        self.__name__ = getattr(func, "__name__", "track")
        self.__doc__ = getattr(func, "__doc__", None)
        self.loop = bool(loop)
        self.loop_times = loop_times
        self.bpm = float(bpm)
        self.seed = int(seed)

    def __call__(self, *args: object, **kwargs: object) -> Track:
        active = _CURRENT_BUILDER.get()
        if active is not None:
            call_id = _next_node_id()
            child = active.child()
            bound_args = tuple(_bind_track_call_value(arg, call_id) for arg in args)
            bound_kwargs = {
                name: _bind_track_call_value(value, call_id) for name, value in kwargs.items()
            }
            token = _CURRENT_BUILDER.set(child)
            try:
                result = self.func(*bound_args, **bound_kwargs)
            finally:
                _CURRENT_BUILDER.reset(token)
            if result is not None:
                raise SynthPlanError("@sy.track functions must build actions and return None.")
            active.nodes.append(
                CallNode(
                    id=call_id,
                    name=self.__name__,
                    body=tuple(child.nodes),
                    beat=active.current_beat,
                    body_beats=child.current_beat,
                )
            )
            active.current_beat += child.current_beat
            return Track(self, TrackPlan(self.__name__, (), 0.0, self.loop, self.loop_times))
        return self.build(*args, **kwargs)

    def build(self, *args: object, **kwargs: object) -> Track:
        """Build and return a logical track plan."""

        builder = PlanBuilder(bpm=self.bpm, seed=self.seed)
        token = _CURRENT_BUILDER.set(builder)
        try:
            result = self.func(*args, **kwargs)
        finally:
            _CURRENT_BUILDER.reset(token)
        if result is not None:
            raise SynthPlanError("@sy.track functions must build actions and return None.")
        plan = TrackPlan(
            self.__name__,
            tuple(builder.nodes),
            builder.current_beat,
            loop=self.loop,
            loop_times=self.loop_times,
            bpm=builder.bpm,
            seed=builder.seed,
        )
        return Track(self, plan)


@overload
def track(
    func: None = None,
    *,
    loop: bool = False,
    loop_times: int | None = None,
    bpm: float = 60.0,
    seed: int = 0,
) -> Callable[[_TrackFunction], TrackDefinition]: ...


@overload
def track(
    func: _TrackFunction,
    *,
    loop: bool = False,
    loop_times: int | None = None,
    bpm: float = 60.0,
    seed: int = 0,
) -> TrackDefinition: ...


def track(
    func: _TrackFunction | None = None,
    *,
    loop: bool = False,
    loop_times: int | None = None,
    bpm: float = 60.0,
    seed: int = 0,
) -> Callable[[_TrackFunction], TrackDefinition] | TrackDefinition:
    """Decorate a function as a logical synth track.

    The decorator may be used as ``@sy.track`` or ``@sy.track(loop=True)``. The
    resulting object is callable. Outside another track it returns a built
    :class:`Track`; inside another track it inlines the decorated function into
    the active logical plan.
    """

    def decorate(inner: _TrackFunction) -> TrackDefinition:
        definition = TrackDefinition(inner, loop=loop, loop_times=loop_times, bpm=bpm, seed=seed)
        package = sys.modules.get("gummysnake.synth")
        if package is not None and not hasattr(package, definition.__name__):
            setattr(package, definition.__name__, definition)
        return definition

    if func is not None:
        return decorate(func)
    return decorate


@dataclass(slots=True)
class _RenderedTrackCacheEntry:
    payload: bytes
    duration_seconds: float
    path: Path | None = None


@dataclass(slots=True)
class _RenderedFileSoundSource:
    duration: float


def _event_time_groups(
    events: Sequence[ScheduledEvent], *, tolerance: float = 1e-9
) -> tuple[tuple[ScheduledEvent, ...], ...]:
    """Group adjacent events that should start at the same realtime instant."""

    groups: list[list[ScheduledEvent]] = []
    for event in events:
        if not groups or abs(event.time_seconds - groups[-1][0].time_seconds) > tolerance:
            groups.append([event])
        else:
            groups[-1].append(event)
    return tuple(tuple(group) for group in groups)


class TrackPlayback:
    """Realtime playback handle returned by track playback methods."""

    def __init__(
        self,
        plan: PhysicalPlan | None,
        *,
        logical_plan: TrackPlan | None = None,
        sample_rate: int = _SAMPLE_RATE,
        player_factory: Any | None = None,
        look_ahead: float = 0.05,
        name: str = "gummysnake-track",
        rolling: bool = False,
        window_seconds: float = 4.0,
        rendered_cache: _RenderedTrackCacheEntry | None = None,
    ) -> None:
        self._plan = plan
        self._logical_plan = logical_plan
        self._rolling = bool(rolling)
        self._window_seconds = max(0.25, float(window_seconds))
        self._rendered_cache = rendered_cache
        self._sample_rate = int(sample_rate)
        self._player_factory = player_factory
        self._look_ahead = max(0.0, float(look_ahead))
        self._name = name
        self._stop_event = threading.Event()
        self._done_event = threading.Event()
        self._error: Exception | None = None
        self._active_sounds: list[tuple[Sound, float]] = []
        self._rust_playback: Any | None = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"gummysnake-synth-{name}",
            daemon=True,
        )

    def start(self) -> TrackPlayback:
        """Start scheduling playback on a background thread."""

        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop scheduling and close any active event sounds."""

        self._stop_event.set()
        self._close_rust_playback()
        self._close_active_sounds()

    def join(self, timeout: float | None = None) -> bool:
        """Wait for playback to finish.

        Returns:
            ``True`` when playback finished before the timeout.
        """

        self._thread.join(timeout)
        return not self._thread.is_alive()

    def wait_until_stop(self, timeout: float | None = None) -> bool:
        """Block until playback stops or an optional timeout expires.

        This is a readability-focused alias for :meth:`join` intended for
        scripts and examples that start a track and then keep the process alive
        until the bounded playback finishes.
        """

        return self.join(timeout)

    def is_playing(self) -> bool:
        """Return whether the realtime scheduler is still active."""

        return not self._done_event.is_set()

    @property
    def error(self) -> Exception | None:
        """Playback error captured from the scheduler thread, if any."""

        return self._error

    def _run(self) -> None:
        try:
            if self._rolling:
                self._run_rolling()
            else:
                self._run_finite()
        except Exception as exc:  # pragma: no cover - backend/audio-device dependent
            self._error = exc
        finally:
            self._close_rust_playback()
            self._close_active_sounds()
            self._done_event.set()

    def _run_finite(self) -> None:
        if self._plan is None:
            raise SynthPlanError("Finite realtime playback requires a physical plan.")
        cached = self._rendered_cache
        if self._player_factory is None:
            self._run_finite_rust_playback(cached)
            return
        if cached is not None:
            payload = cached.payload
            seconds = cached.duration_seconds
        else:
            payload = _render_physical_plan(self._plan, sample_rate=self._sample_rate)
            seconds = _wav_duration_seconds(payload)
        if self._stop_event.is_set():
            return
        if seconds <= 0:
            return
        if cached is not None and cached.path is not None and cached.path.exists():
            sound = Sound(
                _RenderedFileSoundSource(seconds),
                path=cached.path,
                player_factory=self._player_factory,
            )
        else:
            sound = Sound(
                MemorySoundSource(payload, duration=seconds),
                path=Path(f"{self._name}.wav"),
                player_factory=self._player_factory,
            )
        start_time = time.monotonic()
        target_end_time = start_time + max(0.0, self._plan.duration_seconds)
        sound.play()
        self._active_sounds.append((sound, start_time + seconds + 0.25))
        self._wait_until_finite_end(target_end_time)

    def _run_finite_rust_playback(self, cached: _RenderedTrackCacheEntry | None) -> None:
        if self._plan is None:
            raise SynthPlanError("Finite realtime playback requires a physical plan.")
        _ = cached
        runtime = _require_synth_runtime()
        playback = runtime.synth_play_serialized_plan(self._plan.to_bytes(), int(self._sample_rate))
        self._rust_playback = playback
        if self._stop_event.is_set():
            self._close_rust_playback()
            return
        target_end_time = time.monotonic() + max(0.0, self._plan.duration_seconds)
        self._wait_until_finite_end(target_end_time)

    def _run_rolling(self) -> None:
        if self._logical_plan is None:
            raise SynthPlanError("Rolling realtime playback requires a logical plan.")
        start_time = time.monotonic()
        emitted: set[tuple[object, ...]] = set()
        horizon = 0.0
        while not self._stop_event.is_set():
            elapsed = max(0.0, time.monotonic() - start_time)
            horizon = max(horizon + self._window_seconds, elapsed + self._window_seconds)
            plan = _expand_physical_plan(self._logical_plan, horizon)
            controls_by_instance, fx_controls = _control_lookup(plan)
            events = [
                event
                for event in sorted(plan.events, key=lambda item: item.time_seconds)
                if event.instance not in emitted and event.time_seconds <= horizon
            ]
            if not events:
                self._close_finished_sounds(time.monotonic())
                self._stop_event.wait(0.05)
                continue
            for event_group in _event_time_groups(events):
                if self._stop_event.is_set():
                    break
                for event in event_group:
                    emitted.add(event.instance)
                self._schedule_event_group(
                    start_time, event_group, controls_by_instance, fx_controls
                )
            self._close_finished_sounds(time.monotonic())
        self._wait_for_active_sounds()

    def _schedule_event_group(
        self,
        start_time: float,
        events: Sequence[ScheduledEvent],
        controls_by_instance: Mapping[tuple[object, ...], Sequence[ScheduledControl]],
        fx_controls: Mapping[int, Sequence[ScheduledControl]],
    ) -> None:
        if not events:
            return
        event_time = events[0].time_seconds
        self._sleep_until(start_time + max(0.0, event_time - self._look_ahead))
        if self._stop_event.is_set():
            return
        sounds = self._render_event_group_sounds(events, controls_by_instance, fx_controls)
        if not sounds:
            return
        self._sleep_until(start_time + event_time)
        if self._stop_event.is_set():
            for _event, sound in sounds:
                sound.close()
            return
        self._play_event_sounds(start_time, event_time, sounds)

    def _render_event_group_sounds(
        self,
        events: Sequence[ScheduledEvent],
        controls_by_instance: Mapping[tuple[object, ...], Sequence[ScheduledControl]],
        fx_controls: Mapping[int, Sequence[ScheduledControl]],
    ) -> list[tuple[ScheduledEvent, Sound]]:
        sounds: list[tuple[ScheduledEvent, Sound]] = []
        for event in events:
            if self._stop_event.is_set():
                break
            sound = _render_event_sound(
                event,
                controls_by_instance.get(event.instance, ()),
                fx_controls,
                self._sample_rate,
                self._player_factory,
                self._name,
            )
            if sound is not None:
                sounds.append((event, sound))
        return sounds

    def _play_event_sounds(
        self,
        start_time: float,
        event_time: float,
        sounds: Sequence[tuple[ScheduledEvent, Sound]],
    ) -> None:
        for _event, sound in sounds:
            sound.play()
            end_time = event_time + (sound.duration or 0.0) + 0.25
            self._active_sounds.append((sound, start_time + end_time))
        self._close_finished_sounds(time.monotonic())

    def _wait_for_active_sounds(self) -> None:
        while self._active_sounds and not self._stop_event.is_set():
            self._close_finished_sounds(time.monotonic())
            if self._active_sounds:
                self._stop_event.wait(0.05)

    def _wait_until_finite_end(self, target_time: float) -> None:
        while not self._stop_event.is_set():
            self._raise_if_rust_playback_failed()
            now = time.monotonic()
            self._close_finished_sounds(now)
            remaining = target_time - now
            if remaining <= 0:
                return
            self._stop_event.wait(min(remaining, 0.05))

    def _raise_if_rust_playback_failed(self) -> None:
        playback = self._rust_playback
        if playback is None:
            return
        error_message = getattr(playback, "error", None)
        if callable(error_message):
            error_message = error_message()
        if error_message:
            raise RuntimeError(f"Rust synth playback failed: {error_message}")

    def _sleep_until(self, target_time: float) -> None:
        while not self._stop_event.is_set():
            remaining = target_time - time.monotonic()
            if remaining <= 0:
                return
            self._stop_event.wait(min(remaining, 0.05))

    def _close_finished_sounds(self, now: float) -> None:
        remaining: list[tuple[Sound, float]] = []
        for sound, end_time in self._active_sounds:
            if now >= end_time:
                sound.close()
            else:
                remaining.append((sound, end_time))
        self._active_sounds = remaining

    def _close_active_sounds(self) -> None:
        sounds = self._active_sounds
        self._active_sounds = []
        for sound, _end_time in sounds:
            with contextlib.suppress(Exception):
                sound.close()

    def _close_rust_playback(self) -> None:
        playback = self._rust_playback
        self._rust_playback = None
        if playback is None:
            return
        close = getattr(playback, "close", None)
        stop = getattr(playback, "stop", None)
        with contextlib.suppress(Exception):
            if callable(close):
                close()
            elif callable(stop):
                stop()


@dataclass(slots=True)
class Track:
    """Built logical track with physical-plan, save, playback, and Sound helpers."""

    definition: TrackDefinition | SynthDefinition | FxDefinition
    logical_plan: TrackPlan
    _render_cache: dict[tuple[float, int], _RenderedTrackCacheEntry] = field(
        default_factory=dict, init=False, repr=False
    )

    def explain(self) -> str:
        """Return the logical-plan explanation."""

        return self.logical_plan.explain()

    def physical_plan(self, duration: Duration | float | None = None) -> PhysicalPlan:
        """Expand the logical plan into concrete events and controls."""

        return _expand_physical_plan(
            self.logical_plan, _duration_seconds_or_default(duration, self)
        )

    def render(
        self, duration: Duration | float | None = None, *, sample_rate: int = _SAMPLE_RATE
    ) -> bytes:
        """Render the track to 16-bit stereo PCM WAV bytes."""

        duration_seconds = _duration_seconds_or_default(duration, self)
        cache_key = (duration_seconds, int(sample_rate))
        if cached := self._render_cache.get(cache_key):
            return cached.payload
        plan = _expand_physical_plan(self.logical_plan, duration_seconds)
        payload = _render_physical_plan(plan, sample_rate=sample_rate)
        self._render_cache[cache_key] = _RenderedTrackCacheEntry(
            payload, _wav_duration_seconds(payload)
        )
        return payload

    def save(
        self,
        path: str | Path,
        *,
        format: Format | str | None = None,  # noqa: A002
        duration: Duration | float | None = None,
        sample_rate: int = _SAMPLE_RATE,
    ) -> Path:
        """Render or serialize and save the track.

        ``.gss`` and ``.gsfx`` output store the expanded physical plan as a binary
        serialized artifact. WAV output is dependency-free. MP3 output requires ``ffmpeg`` and
        raises a capability error when it is unavailable.
        """

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_format = _resolve_format(output_path, format)
        duration_seconds = _duration_seconds_or_default(duration, self)
        if resolved_format in {Format.GSS, Format.GSFX}:
            base_plan = _expand_physical_plan(self.logical_plan, duration_seconds)
            plan = PhysicalPlan(
                base_plan.events,
                base_plan.controls,
                base_plan.duration_seconds,
                int(sample_rate),
            )
            plan.save(
                output_path,
                metadata={
                    "track": self.logical_plan.name,
                    "sample_rate": sample_rate,
                    "source": "Track.save",
                },
            )
            return output_path
        wav_payload = self.render(duration_seconds, sample_rate=sample_rate)
        if resolved_format == Format.WAV:
            output_path.write_bytes(wav_payload)
            cache_key = (duration_seconds, int(sample_rate))
            cached = self._render_cache.get(cache_key)
            if cached is not None:
                cached.path = output_path
            return output_path
        _write_mp3_with_ffmpeg(wav_payload, output_path)
        return output_path

    def to_sound(
        self,
        path: str | Path = "generated-track.wav",
        *,
        duration: Duration | float | None = None,
        sample_rate: int = _SAMPLE_RATE,
    ) -> Sound:
        """Render the track into an in-memory :class:`gummysnake.Sound`."""

        payload = self.render(duration, sample_rate=sample_rate)
        seconds = _wav_duration_seconds(payload)
        return Sound(MemorySoundSource(payload, duration=seconds), path=Path(path))

    def play(
        self,
        *,
        duration: Duration | float | None = None,
        sample_rate: int = _SAMPLE_RATE,
        realtime: bool = True,
        look_ahead: float = 0.05,
        player_factory: Any | None = None,
    ) -> TrackPlayback | Sound:
        """Start playback and return a handle.

        By default, bounded direct playback starts a Rust SDL audio stream from
        the serialized physical plan and renders playback windows on demand,
        rather than pre-rendering the whole track before audio starts. Call
        ``wait_until_stop()`` on the returned ``TrackPlayback`` to block until
        bounded playback finishes.
        """

        if not realtime:
            rendered = self.to_sound(duration=duration, sample_rate=sample_rate)
            rendered.play()
            return rendered
        rolling = duration is None and _should_play_as_rolling_loop(self.logical_plan)
        duration_seconds = None if rolling else _duration_seconds_or_default(duration, self)
        rendered_cache = (
            None
            if rolling or duration_seconds is None
            else self._render_cache.get((duration_seconds, int(sample_rate)))
        )
        playback = TrackPlayback(
            None
            if rolling or duration_seconds is None
            else _expand_physical_plan(self.logical_plan, duration_seconds),
            logical_plan=self.logical_plan if rolling else None,
            sample_rate=sample_rate,
            player_factory=player_factory,
            look_ahead=look_ahead,
            name=self.logical_plan.name,
            rolling=rolling,
            rendered_cache=rendered_cache,
        )
        return playback.start()


# Backwards-compatible alias for people looking for a plan class in docs/tests.
TrackInstance = Track


def load_physical_plan(path: str | Path) -> PhysicalPlan:
    """Load a binary ``.gss`` or ``.gsfx`` physical-plan asset."""

    return PhysicalPlan.load(path)


def builtin_synth_names() -> tuple[str, ...]:
    """Return bundled compiled synth names available under ``assets/synths/compiled``."""

    if not _BUILTIN_SYNTH_COMPILED_DIR.exists():
        return ()
    return tuple(sorted(path.stem for path in _BUILTIN_SYNTH_COMPILED_DIR.glob("*.gss")))


def builtin_synth_path(name: str) -> Path:
    """Return the bundled compiled ``.gss`` path for a synth name."""

    normalized = name.strip().removeprefix(":")
    path = _BUILTIN_SYNTH_COMPILED_DIR / f"{normalized}.gss"
    if not path.exists():
        raise ArgumentValidationError(f"No bundled compiled synth asset named {name!r}.")
    return path


def load_builtin_synth_plan(name: str) -> PhysicalPlan:
    """Load a bundled compiled synth physical plan by name."""

    return PhysicalPlan.load(builtin_synth_path(name))


def builtin_fx_names() -> tuple[str, ...]:
    """Return bundled compiled FX names available under ``assets/synths/fx/compiled``."""

    if not _BUILTIN_FX_COMPILED_DIR.exists():
        return ()
    return tuple(sorted(path.stem for path in _BUILTIN_FX_COMPILED_DIR.glob("*.gsfx")))


def builtin_fx_path(name: str) -> Path:
    """Return the bundled compiled ``.gsfx`` path for an FX name."""

    normalized = name.strip().removeprefix(":")
    path = _BUILTIN_FX_COMPILED_DIR / f"{normalized}.gsfx"
    if not path.exists():
        raise ArgumentValidationError(f"No bundled compiled FX asset named {name!r}.")
    return path


def load_builtin_fx_plan(name: str) -> PhysicalPlan:
    """Load a bundled compiled FX physical plan by name."""

    return PhysicalPlan.load(builtin_fx_path(name))


def _should_play_as_rolling_loop(plan: TrackPlan) -> bool:
    return plan.loop_times is None and (plan.loop or _has_open_loop(plan.nodes))


def _duration_seconds_or_default(
    duration_value: Duration | float | None, track_instance: Track
) -> float:
    if isinstance(duration_value, Duration):
        return duration_value.seconds
    if duration_value is not None:
        return float(duration_value)
    plan = track_instance.logical_plan
    if plan.loop or plan.loop_times is not None or _has_open_loop(plan.nodes):
        return max(1.0, _beats_to_seconds(plan.duration_beats or 8.0, plan.bpm))
    return max(0.25, _beats_to_seconds(plan.duration_beats, plan.bpm) + 2.0)


def _append_node_explain(lines: list[str], nodes: Sequence[PlanNode], *, indent: str) -> None:
    for node in nodes:
        if isinstance(node, EventNode):
            fx_names = [fx.name for fx in node.fx_chain]
            lines.append(
                f"{indent}{node.beat:g}: {node.kind} {node.value!r} "
                f"synth={node.synth_name!r} opts={node.opts!r} fx={fx_names!r}"
            )
        elif isinstance(node, SleepNode):
            lines.append(f"{indent}{node.beat:g}: sleep {node.duration_beats!r}")
        elif isinstance(node, ControlNode):
            lines.append(f"{indent}{node.beat:g}: control #{node.target_id} {node.opts!r}")
        elif isinstance(node, BindNode):
            continue
        elif isinstance(node, LoopNode):
            lines.append(
                f"{indent}{node.beat:g}: loop times={node.times} body_beats={node.body_beats:g}"
            )
            _append_node_explain(lines, node.body, indent=indent + "  ")
        elif isinstance(node, ThreadNode):
            lines.append(f"{indent}{node.beat:g}: thread name={node.name!r}")
            _append_node_explain(lines, node.body, indent=indent + "  ")
        elif isinstance(node, CallNode):
            lines.append(f"{indent}{node.beat:g}: call {node.name} body_beats={node.body_beats:g}")
            _append_node_explain(lines, node.body, indent=indent + "  ")


def _has_open_loop(nodes: Sequence[PlanNode]) -> bool:
    for node in nodes:
        if isinstance(node, LoopNode) and (node.times is None or _has_open_loop(node.body)):
            return True
        if isinstance(node, ThreadNode) and _has_open_loop(node.body):
            return True
        if isinstance(node, CallNode) and _has_open_loop(node.body):
            return True
    return False


def _expand_physical_plan(plan: TrackPlan, duration_seconds: float) -> PhysicalPlan:
    duration_beats = duration_seconds * plan.bpm / 60.0
    ctx = EvalContext(_random.Random(plan.seed))
    events: list[ScheduledEvent] = []
    controls: list[ScheduledControl] = []
    root_repetitions = (
        plan.loop_times if plan.loop_times is not None else (None if plan.loop else 1)
    )
    fallback_root_body = plan.duration_beats or duration_beats
    if fallback_root_body <= 0:
        fallback_root_body = duration_beats
    iteration = 0
    start_beat = 0.0
    while True:
        if root_repetitions is not None and iteration >= root_repetitions:
            break
        if start_beat >= duration_beats:
            break
        elapsed_beats = _expand_nodes(
            plan.nodes,
            start_beat=start_beat,
            duration_beats=duration_beats,
            bpm=plan.bpm,
            ctx=ctx,
            events=events,
            controls=controls,
            scope=("root", iteration),
            repeat_scope=(("root", iteration),),
        )
        iteration += 1
        if root_repetitions is not None:
            start_beat += elapsed_beats if elapsed_beats > 0 else fallback_root_body
            continue
        if not plan.loop:
            break
        root_body = elapsed_beats if elapsed_beats > 0 else fallback_root_body
        if root_body <= 0:
            break
        start_beat += root_body
    events.sort(key=lambda event: event.time_seconds)
    controls.sort(key=lambda control: control.time_seconds)
    return PhysicalPlan(tuple(events), tuple(controls), duration_seconds)


def _expand_nodes(
    nodes: Sequence[PlanNode],
    *,
    start_beat: float,
    duration_beats: float,
    bpm: float,
    ctx: EvalContext,
    events: list[ScheduledEvent],
    controls: list[ScheduledControl],
    scope: tuple[object, ...],
    repeat_scope: tuple[object, ...],
) -> float:
    cursor = 0.0
    for node in nodes:
        absolute_beat = start_beat + cursor
        if isinstance(node, EventNode):
            if absolute_beat < duration_beats:
                event_scope = scope
                with _eval_scope(ctx, event_scope, repeat_scope):
                    if node.condition is not None and not bool(resolve_value(node.condition, ctx)):
                        continue
                    instance = (*event_scope, node.id)
                    events.append(
                        ScheduledEvent(
                            instance=instance,
                            node_id=node.id,
                            kind=node.kind,
                            time_seconds=_beats_to_seconds(absolute_beat, bpm),
                            value=resolve_value(node.value, ctx),
                            opts=cast(Mapping[str, object], resolve_value(node.opts, ctx)),
                            synth_name=node.synth_name,
                            synth_opts=cast(
                                Mapping[str, object], resolve_value(node.synth_opts, ctx)
                            ),
                            fx_chain=tuple(
                                FxHandle(
                                    fx.id,
                                    fx.name,
                                    cast(dict[str, object], resolve_value(dict(fx.opts), ctx)),
                                )
                                for fx in node.fx_chain
                            ),
                        )
                    )
        elif isinstance(node, SleepNode):
            with _eval_scope(ctx, scope, repeat_scope):
                duration = _as_float(resolve_value(node.duration_beats, ctx))
            if duration < 0:
                raise ArgumentValidationError("sleep() duration cannot be negative.")
            cursor += duration
        elif isinstance(node, ControlNode):
            if absolute_beat < duration_beats:
                with _eval_scope(ctx, scope, repeat_scope):
                    if node.condition is not None and not bool(resolve_value(node.condition, ctx)):
                        continue
                    controls.append(
                        ScheduledControl(
                            target_instance=(*scope, *node.target_scope_suffix, node.target_id),
                            target_id=node.target_id,
                            time_seconds=_beats_to_seconds(absolute_beat, bpm),
                            opts=cast(Mapping[str, object], resolve_value(node.opts, ctx)),
                        )
                    )
        elif isinstance(node, BindNode):
            if absolute_beat < duration_beats:
                with _eval_scope(ctx, scope, repeat_scope):
                    key = _source_bind_key(ctx, node.repeat_depth, node.id)
                    if key not in ctx.bindings:
                        ctx.bindings[key] = resolve_value(node.source, ctx)
        elif isinstance(node, LoopNode):
            cursor += _expand_loop_node(
                node,
                start_beat=absolute_beat,
                duration_beats=duration_beats,
                bpm=bpm,
                ctx=ctx,
                events=events,
                controls=controls,
                scope=scope,
                repeat_scope=repeat_scope,
            )
        elif isinstance(node, ThreadNode):
            _expand_nodes(
                node.body,
                start_beat=absolute_beat,
                duration_beats=duration_beats,
                bpm=bpm,
                ctx=ctx,
                events=events,
                controls=controls,
                scope=(*scope, node.id, node.name or "thread"),
                repeat_scope=repeat_scope,
            )
        elif isinstance(node, CallNode):
            elapsed = _expand_nodes(
                node.body,
                start_beat=absolute_beat,
                duration_beats=duration_beats,
                bpm=bpm,
                ctx=ctx,
                events=events,
                controls=controls,
                scope=(*scope, ("call", node.id)),
                repeat_scope=repeat_scope,
            )
            cursor += elapsed if elapsed > 0 else node.body_beats
    return cursor


def _expand_loop_node(
    node: LoopNode,
    *,
    start_beat: float,
    duration_beats: float,
    bpm: float,
    ctx: EvalContext,
    events: list[ScheduledEvent],
    controls: list[ScheduledControl],
    scope: tuple[object, ...],
    repeat_scope: tuple[object, ...],
) -> float:
    fallback_body_beats = node.body_beats
    if fallback_body_beats <= 0:
        return 0.0
    max_iterations = node.times
    iteration = 0
    loop_elapsed = 0.0
    first_body_beats: float | None = None
    while True:
        if max_iterations is not None and iteration >= max_iterations:
            break
        loop_start = start_beat + loop_elapsed
        if loop_start >= duration_beats:
            break
        iteration_scope = (*scope, node.id, iteration)
        iteration_repeat_scope = (*repeat_scope, (node.id, iteration))
        body_beats = _expand_nodes(
            node.body,
            start_beat=loop_start,
            duration_beats=duration_beats,
            bpm=bpm,
            ctx=ctx,
            events=events,
            controls=controls,
            scope=iteration_scope,
            repeat_scope=iteration_repeat_scope,
        )
        if body_beats <= 0:
            body_beats = fallback_body_beats
        if body_beats <= 0:
            break
        if first_body_beats is None:
            first_body_beats = body_beats
        loop_elapsed += body_beats
        iteration += 1
    if max_iterations is None:
        return first_body_beats if first_body_beats is not None else fallback_body_beats
    return loop_elapsed


def _beats_to_seconds(beats: float, bpm: float) -> float:
    return beats * 60.0 / bpm


def _render_physical_plan(plan: PhysicalPlan, *, sample_rate: int = _SAMPLE_RATE) -> bytes:
    runtime = _require_synth_runtime()
    return bytes(runtime.synth_render_serialized_plan_wav(plan.to_bytes(), int(sample_rate)))


def _require_synth_runtime() -> Any:
    from gummysnake.rust.canvas import require_canvas_runtime

    runtime = require_canvas_runtime()
    if (
        not hasattr(runtime, "synth_render_serialized_plan_wav")
        or not hasattr(runtime, "synth_play_serialized_plan")
        or not hasattr(runtime, "synth_play_wav_bytes")
        or not hasattr(runtime, "synth_render_plan_wav")
        or not hasattr(runtime, "synth_render_event_wav")
        or not hasattr(runtime, "synth_sample_duration")
    ):
        raise BackendCapabilityError(
            "Synth rendering requires a current gummysnake.rust._canvas runtime. "
            "Rebuild it with: uvx maturin develop --release --manifest-path "
            "crates/gummy_canvas/Cargo.toml --features extension-module"
        )
    return runtime


def _event_payloads(plan: PhysicalPlan) -> list[dict[str, object]]:
    controls_by_instance, fx_controls = _control_lookup(plan)
    return [
        _event_payload(
            event,
            controls_by_instance.get(event.instance, ()),
            fx_controls,
        )
        for event in plan.events
    ]


def _scheduled_event_to_dict(event: ScheduledEvent) -> dict[str, object]:
    return {
        "instance": [_serialize_synth_value(item) for item in event.instance],
        "node_id": event.node_id,
        "kind": event.kind,
        "time_seconds": event.time_seconds,
        "value": _serialize_synth_value(event.value),
        "opts": _serialize_opts(event.opts),
        "synth_name": event.synth_name,
        "synth_opts": _serialize_opts(event.synth_opts),
        "fx_chain": [
            {"id": fx.id, "name": fx.name, "opts": _serialize_opts(fx.opts)}
            for fx in event.fx_chain
        ],
    }


def _scheduled_control_to_dict(control: ScheduledControl) -> dict[str, object]:
    return {
        "target_instance": [_serialize_synth_value(item) for item in control.target_instance],
        "target_id": control.target_id,
        "time_seconds": control.time_seconds,
        "opts": _serialize_opts(control.opts),
    }


def _scheduled_event_from_dict(value: object) -> ScheduledEvent:
    if not isinstance(value, Mapping):
        raise ArgumentValidationError("Serialized synth event must be an object.")
    mapping = cast(Mapping[str, object], value)
    kind = mapping.get("kind", "play")
    if kind not in {"play", "sample"}:
        raise ArgumentValidationError(f"Serialized synth event kind {kind!r} is not supported.")
    fx_value = mapping.get("fx_chain", ())
    if not isinstance(fx_value, Sequence) or isinstance(fx_value, str | bytes):
        raise ArgumentValidationError("Serialized synth event fx_chain must be a list.")
    return ScheduledEvent(
        instance=_deserialize_instance(mapping.get("instance", ())),
        node_id=_as_int(mapping.get("node_id", 0)),
        kind=cast(Literal["play", "sample"], kind),
        time_seconds=_as_float(mapping.get("time_seconds", 0.0)),
        value=_deserialize_plan_value(mapping.get("value")),
        opts=cast(Mapping[str, object], _deserialize_plan_value(mapping.get("opts", {}))),
        synth_name=str(mapping.get("synth_name", "beep")),
        synth_opts=cast(
            Mapping[str, object], _deserialize_plan_value(mapping.get("synth_opts", {}))
        ),
        fx_chain=tuple(_fx_handle_from_dict(item) for item in fx_value),
    )


def _scheduled_control_from_dict(value: object) -> ScheduledControl:
    if not isinstance(value, Mapping):
        raise ArgumentValidationError("Serialized synth control must be an object.")
    mapping = cast(Mapping[str, object], value)
    return ScheduledControl(
        target_instance=_deserialize_instance(mapping.get("target_instance", ())),
        target_id=_as_int(mapping.get("target_id", 0)),
        time_seconds=_as_float(mapping.get("time_seconds", 0.0)),
        opts=cast(Mapping[str, object], _deserialize_plan_value(mapping.get("opts", {}))),
    )


def _fx_handle_from_dict(value: object) -> FxHandle:
    if not isinstance(value, Mapping):
        raise ArgumentValidationError("Serialized synth FX handle must be an object.")
    mapping = cast(Mapping[str, object], value)
    return FxHandle(
        id=_as_int(mapping.get("id", 0)),
        name=str(mapping.get("name", "level")),
        opts=cast(dict[str, object], _deserialize_plan_value(mapping.get("opts", {}))),
    )


def _deserialize_instance(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(_freeze_instance_part(item) for item in value)
    return (_freeze_instance_part(value),)


def _freeze_instance_part(value: object) -> object:
    if isinstance(value, list | tuple):
        return tuple(_freeze_instance_part(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze_instance_part(item)) for key, item in value.items()))
    return value


def _deserialize_plan_value(value: object) -> object:
    if isinstance(value, list):
        return [_deserialize_plan_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _deserialize_plan_value(item) for key, item in value.items()}
    return value


def _control_lookup(
    plan: PhysicalPlan,
) -> tuple[
    dict[tuple[object, ...], list[ScheduledControl]],
    dict[int, list[ScheduledControl]],
]:
    controls_by_instance: dict[tuple[object, ...], list[ScheduledControl]] = {}
    fx_controls: dict[int, list[ScheduledControl]] = {}
    for control_node in plan.controls:
        controls_by_instance.setdefault(control_node.target_instance, []).append(control_node)
        fx_controls.setdefault(control_node.target_id, []).append(control_node)
    return controls_by_instance, fx_controls


def _event_payload(
    event: ScheduledEvent,
    controls: Sequence[ScheduledControl],
    fx_controls: Mapping[int, Sequence[ScheduledControl]],
) -> dict[str, object]:
    return {
        "node_id": event.node_id,
        "kind": event.kind,
        "time_seconds": event.time_seconds,
        "value": _serialize_event_value(event),
        "opts": _serialize_opts(event.opts),
        "synth_name": event.synth_name,
        "synth_opts": _serialize_opts(event.synth_opts),
        "fx_chain": [
            {
                "id": fx.id,
                "name": fx.name,
                "opts": _serialize_opts(
                    {
                        **fx.opts,
                        **_fx_opts_at(fx, event.time_seconds, fx_controls.get(fx.id, ())),
                    }
                ),
            }
            for fx in event.fx_chain
        ],
        "controls": [
            {
                "time_seconds": control_node.time_seconds,
                "opts": _serialize_opts(control_node.opts),
            }
            for control_node in controls
        ],
    }


def _serialize_opts(opts: Mapping[str, object]) -> dict[str, object]:
    return {str(name): _serialize_synth_value(value) for name, value in opts.items()}


def _serialize_event_value(event: ScheduledEvent) -> object:
    if event.kind != "sample":
        return _serialize_synth_value(event.value)
    return _serialize_sample_value(event.value)


def _serialize_sample_value(value: object) -> object:
    if isinstance(value, Ring | list | tuple):
        values = list(value)
        if not values:
            return []
        return [_serialize_synth_value(_resolve_sample_source(values[0]))] + [
            _serialize_synth_value(item) for item in values[1:]
        ]
    return _serialize_synth_value(_resolve_sample_source(value))


def _serialize_synth_value(value: object) -> object:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Ring | list | tuple):
        return [_serialize_synth_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _serialize_synth_value(item) for key, item in value.items()}
    return str(value)


def _render_event_sound(
    event: ScheduledEvent,
    controls: Sequence[ScheduledControl],
    fx_controls: Mapping[int, Sequence[ScheduledControl]],
    sample_rate: int,
    player_factory: Any | None,
    name: str,
) -> Sound | None:
    runtime = _require_synth_runtime()
    payload = bytes(
        runtime.synth_render_event_wav(
            _event_payload(event, controls, fx_controls),
            int(sample_rate),
        )
    )
    if not payload:
        return None
    seconds = _wav_duration_seconds(payload)
    if seconds <= 0:
        return None
    return Sound(
        MemorySoundSource(payload, duration=seconds),
        path=Path(f"{name}-event-{event.node_id}.wav"),
        player_factory=player_factory,
    )


def _fx_opts_at(
    handle: FxHandle, event_time: float, controls: Sequence[ScheduledControl]
) -> dict[str, object]:
    opts = dict(handle.opts)
    for control_node in controls:
        if control_node.time_seconds <= event_time + 1e-9:
            opts.update(control_node.opts)
    return opts


_BUILTIN_SAMPLE_DURATIONS = {
    "loop_amen": 1.753310657596372,
    "loop_garzul": 4.0,
    "loop_industrial": 4.0,
    "loop_mika": 4.0,
    "ambi_choir": 3.2,
    "ambi_drone": 4.0,
    "ambi_lunar_land": 5.0,
    "drum_heavy_kick": 0.45,
    "drum_bass_hard": 0.35,
    "drum_cymbal_closed": 0.25,
    "drum_cymbal_open": 1.0,
    "drum_cymbal_soft": 0.5,
    "drum_snare_hard": 0.35,
    "bass_hit_c": 0.55,
    "bass_trance_c": 1.0,
    "bass_voxy_hit_c": 0.7,
    "elec_plip": 0.2,
    "elec_blup": 0.25,
    "elec_blip2": 0.18,
    "elec_beep": 0.18,
    "elec_flip": 0.2,
    "elec_hi_snare": 0.25,
    "elec_snare": 0.25,
    "elec_filt_snare": 0.25,
    "perc_bell": 1.2,
    "guit_em9": 3.0,
    "bd_haus": 0.4,
    "bd_boom": 1.0,
    "bd_ada": 0.35,
    "misc_burp": 0.6,
}


def _sample_duration_seconds(value: object, opts: Mapping[str, object]) -> float:
    # Metadata-only helper; actual audio rendering is Rust-owned.
    name = value[0] if isinstance(value, tuple) and value else value
    resolved_name = _resolve_sample_source(name)
    if isinstance(resolved_name, Path) or (
        isinstance(resolved_name, str) and Path(resolved_name).exists()
    ):
        base = float(_require_synth_runtime().synth_sample_duration(str(resolved_name)))
    elif isinstance(name, Path) or (isinstance(name, str) and Path(name).exists()):
        base = float(_require_synth_runtime().synth_sample_duration(str(name)))
    else:
        base = _BUILTIN_SAMPLE_DURATIONS.get(str(name).removeprefix(":"), 0.5)
    start = _as_float(opts.get("start", 0.0) or 0.0)
    finish = _as_float(opts.get("finish", 1.0) or 1.0)
    fraction = abs(finish - start)
    if "beat_stretch" in opts:
        return _as_float(opts["beat_stretch"])
    rate_value = _as_float(opts.get("rate", 1.0) or 1.0)
    if "rpitch" in opts:
        rate_value *= 2.0 ** (_as_float(opts["rpitch"]) / 12.0)
    return base * max(0.0, fraction) / max(0.0001, abs(rate_value))


def _wav_duration_seconds(payload: bytes) -> float:
    with wave.open(io.BytesIO(payload), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())


def _resolve_format(path: Path, format_value: Format | str | None) -> Format:
    if format_value is not None:
        return Format(format_value)
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "gss":
        return Format.GSS
    if suffix == "gsfx":
        return Format.GSFX
    if suffix == "mp3":
        return Format.MP3
    return Format.WAV


def _write_mp3_with_ffmpeg(wav_payload: bytes, output_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise BackendCapabilityError(
            "MP3 export requires ffmpeg on PATH. Save WAV or install ffmpeg."
        )
    with tempfile.NamedTemporaryFile(
        prefix="gummysnake-synth-", suffix=".wav", delete=False
    ) as file:
        file.write(wav_payload)
        temp_path = Path(file.name)
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(temp_path), str(output_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise BackendCapabilityError(f"ffmpeg could not export MP3 to {output_path!s}.") from exc
    finally:
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)


__all__ = [
    "Duration",
    "Format",
    "FxDefinition",
    "FxHandle",
    "FxSignal",
    "NodeHandle",
    "PhysicalPlan",
    "Ring",
    "SynthDefinition",
    "SynthPlanError",
    "SynthSignal",
    "Track",
    "TrackDefinition",
    "TrackInstance",
    "TrackPlan",
    "TrackPlayback",
    "bools",
    "builtin_fx_names",
    "builtin_fx_path",
    "builtin_synth_names",
    "builtin_synth_path",
    "chord",
    "choose",
    "control",
    "dice",
    "duration",
    "fx",
    "fx_input",
    "fx_output",
    "knit",
    "line",
    "load_builtin_fx_plan",
    "load_builtin_synth_plan",
    "load_physical_plan",
    "look",
    "loop",
    "note",
    "note_frequency",
    "octs",
    "one_in",
    "play",
    "rand",
    "rand_i",
    "range",
    "ring",
    "rrand",
    "rrand_i",
    "sample",
    "sample_duration",
    "scale",
    "sleep",
    "spread",
    "synth",
    "synth_input",
    "synth_output",
    "thread",
    "tick",
    "track",
    "use_synth",
    "when",
]
