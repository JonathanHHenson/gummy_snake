from __future__ import annotations

import builtins
import contextlib
import random as _random
from collections.abc import Iterator, Mapping, Sequence
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

from gummysnake.exceptions import ArgumentValidationError
from gummysnake.synth.synth_runtime.expressions import (
    BinaryExpression,
    ChoiceExpression,
    LiteralExpression,
    SourceBoundExpression,
)
from gummysnake.synth.synth_runtime.lazy_values import (
    SampleDurationExpression,
    TickExpression,
    resolve_value,
)
from gummysnake.synth.synth_runtime.logical_nodes import (
    ControlNode,
    EventNode,
    LoopNode,
    PlanNode,
    SleepNode,
)
from gummysnake.synth.synth_runtime.runtime_foundation import (
    EvalContext,
    Expression,
    SynthPlanError,
    _as_float,
)
from gummysnake.synth.synth_runtime.scales_and_specs import (
    _FX_DEFINITION_CAPTURE,
    FxHandle,
    SynthSpec,
)

if TYPE_CHECKING:
    from gummysnake.synth.synth_runtime.plan_builder import PlanBuilder


def _remap_compiled_fx_chain(
    fx_chain: Sequence[FxHandle], fx_id_map: dict[int, int]
) -> tuple[FxHandle, ...]:
    remapped: list[FxHandle] = []
    for handle in fx_chain:
        if handle.id not in fx_id_map:
            fx_id_map[handle.id] = _next_node_id()
        remapped.append(FxHandle(fx_id_map[handle.id], handle.name, dict(handle.opts)))
    return tuple(remapped)


def _compiled_timeline_nodes(
    timeline_items: Sequence[tuple[float, int, PlanNode]],
    bpm: float,
    duration_seconds: float,
) -> tuple[tuple[PlanNode, ...], float]:
    nodes: list[PlanNode] = []
    cursor_beats = 0.0
    for time_seconds, _order, node in sorted(timeline_items, key=lambda item: (item[0], item[1])):
        beat = max(0.0, time_seconds) * bpm / 60.0
        if beat > cursor_beats:
            nodes.append(SleepNode(cursor_beats, beat - cursor_beats))
            cursor_beats = beat
        if isinstance(node, EventNode | ControlNode):
            node.beat = cursor_beats
        nodes.append(node)
    return tuple(nodes), max(cursor_beats, max(0.0, duration_seconds) * bpm / 60.0)


def _apply_template_parameters(
    event_payloads: list[dict[str, object]],
    control_payloads: list[dict[str, object]],
    opts: Mapping[str, object],
    metadata: Mapping[str, object],
) -> set[str]:
    consumed: set[str] = set()
    parameters = metadata.get("template_parameters", ())
    if not isinstance(parameters, Sequence) or isinstance(parameters, str | bytes | bytearray):
        return consumed
    roots: dict[str, object] = {"events": event_payloads, "controls": control_payloads}
    for parameter in parameters:
        if not isinstance(parameter, Mapping):
            continue
        name = parameter.get("name")
        paths = parameter.get("paths", ())
        if not isinstance(name, str) or name not in opts:
            continue
        if not isinstance(paths, Sequence) or isinstance(paths, str | bytes | bytearray):
            continue
        for path in paths:
            if isinstance(path, Sequence) and not isinstance(path, str | bytes | bytearray):
                _set_template_path(roots, path, opts[name])
        consumed.add(name)
    return consumed


def _set_template_path(root: object, path: Sequence[object], value: object) -> None:
    if not path:
        return
    current = root
    for part in path[:-1]:
        if isinstance(current, Mapping):
            current = cast(Mapping[object, object], current)[part]
        elif isinstance(current, list) and isinstance(part, int):
            current_list = cast(list[object], current)
            current = current_list[int(part)]
        else:
            return
    final = path[-1]
    if isinstance(current, dict):
        current[final] = value
        return
    if isinstance(current, list) and isinstance(final, int):
        current_list = cast(list[object], current)
        current_list[int(final)] = value


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
