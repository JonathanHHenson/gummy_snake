from __future__ import annotations

import random as _random
from collections.abc import Mapping, Sequence
from typing import Any, cast

from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError
from gummysnake.synth.synth_runtime.composition.builder_context import _eval_scope
from gummysnake.synth.synth_runtime.composition.logical_nodes import (
    BindNode,
    CallNode,
    ControlNode,
    EventNode,
    LoopNode,
    PlanNode,
    ScheduledControl,
    ScheduledEvent,
    SleepNode,
    ThreadNode,
    TrackPlan,
)
from gummysnake.synth.synth_runtime.physical.physical_plan import PhysicalPlan
from gummysnake.synth.synth_runtime.physical.serialization import _control_lookup, _event_payload
from gummysnake.synth.synth_runtime.values.foundation import (
    _SAMPLE_RATE,
    EvalContext,
    _as_float,
)
from gummysnake.synth.synth_runtime.values.lazy_values import _source_bind_key, resolve_value
from gummysnake.synth.synth_runtime.values.scales_and_specs import FxHandle


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
    events.sort(key=lambda event: (event.time_seconds, event.order))
    controls.sort(key=lambda control: (control.time_seconds, control.order))
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
    """Expand one logical sequence while preserving its timeline cursor."""

    cursor = 0.0
    for node in nodes:
        absolute_beat = start_beat + cursor
        if isinstance(node, EventNode):
            _expand_event_node(
                node,
                absolute_beat=absolute_beat,
                duration_beats=duration_beats,
                bpm=bpm,
                ctx=ctx,
                events=events,
                controls=controls,
                scope=scope,
                repeat_scope=repeat_scope,
            )
        elif isinstance(node, SleepNode):
            cursor += _expand_sleep_node(node, ctx=ctx, scope=scope, repeat_scope=repeat_scope)
        elif isinstance(node, ControlNode):
            _expand_control_node(
                node,
                absolute_beat=absolute_beat,
                duration_beats=duration_beats,
                bpm=bpm,
                ctx=ctx,
                events=events,
                controls=controls,
                scope=scope,
                repeat_scope=repeat_scope,
            )
        elif isinstance(node, BindNode):
            _expand_bind_node(
                node,
                absolute_beat=absolute_beat,
                duration_beats=duration_beats,
                ctx=ctx,
                scope=scope,
                repeat_scope=repeat_scope,
            )
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
            _expand_thread_node(
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
        elif isinstance(node, CallNode):
            cursor += _expand_call_node(
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
    return cursor


def _expand_event_node(
    node: EventNode,
    *,
    absolute_beat: float,
    duration_beats: float,
    bpm: float,
    ctx: EvalContext,
    events: list[ScheduledEvent],
    controls: list[ScheduledControl],
    scope: tuple[object, ...],
    repeat_scope: tuple[object, ...],
) -> None:
    if absolute_beat >= duration_beats:
        return
    with _eval_scope(ctx, scope, repeat_scope):
        if node.condition is not None and not bool(resolve_value(node.condition, ctx)):
            return
        events.append(
            ScheduledEvent(
                instance=(*scope, node.id),
                node_id=node.id,
                kind=node.kind,
                time_seconds=_beats_to_seconds(absolute_beat, bpm),
                value=resolve_value(node.value, ctx),
                opts=cast(Mapping[str, object], resolve_value(node.opts, ctx)),
                synth_name=node.synth_name,
                synth_opts=cast(Mapping[str, object], resolve_value(node.synth_opts, ctx)),
                fx_chain=tuple(
                    FxHandle(
                        fx.id,
                        fx.name,
                        cast(dict[str, object], resolve_value(dict(fx.opts), ctx)),
                    )
                    for fx in node.fx_chain
                ),
                order=len(events) + len(controls),
            )
        )


def _expand_sleep_node(
    node: SleepNode,
    *,
    ctx: EvalContext,
    scope: tuple[object, ...],
    repeat_scope: tuple[object, ...],
) -> float:
    with _eval_scope(ctx, scope, repeat_scope):
        duration = _as_float(resolve_value(node.duration_beats, ctx))
    if duration < 0:
        raise ArgumentValidationError("sleep() duration cannot be negative.")
    return duration


def _expand_control_node(
    node: ControlNode,
    *,
    absolute_beat: float,
    duration_beats: float,
    bpm: float,
    ctx: EvalContext,
    events: list[ScheduledEvent],
    controls: list[ScheduledControl],
    scope: tuple[object, ...],
    repeat_scope: tuple[object, ...],
) -> None:
    if absolute_beat >= duration_beats:
        return
    with _eval_scope(ctx, scope, repeat_scope):
        if node.condition is not None and not bool(resolve_value(node.condition, ctx)):
            return
        controls.append(
            ScheduledControl(
                target_instance=(*scope, *node.target_scope_suffix, node.target_id),
                target_id=node.target_id,
                time_seconds=_beats_to_seconds(absolute_beat, bpm),
                opts=cast(Mapping[str, object], resolve_value(node.opts, ctx)),
                order=len(events) + len(controls),
            )
        )


def _expand_bind_node(
    node: BindNode,
    *,
    absolute_beat: float,
    duration_beats: float,
    ctx: EvalContext,
    scope: tuple[object, ...],
    repeat_scope: tuple[object, ...],
) -> None:
    if absolute_beat >= duration_beats:
        return
    with _eval_scope(ctx, scope, repeat_scope):
        key = _source_bind_key(ctx, node.repeat_depth, node.id)
        if key not in ctx.bindings:
            ctx.bindings[key] = resolve_value(node.source, ctx)


def _expand_thread_node(
    node: ThreadNode,
    *,
    start_beat: float,
    duration_beats: float,
    bpm: float,
    ctx: EvalContext,
    events: list[ScheduledEvent],
    controls: list[ScheduledControl],
    scope: tuple[object, ...],
    repeat_scope: tuple[object, ...],
) -> None:
    _expand_nodes(
        node.body,
        start_beat=start_beat,
        duration_beats=duration_beats,
        bpm=bpm,
        ctx=ctx,
        events=events,
        controls=controls,
        scope=(*scope, node.id, node.name or "thread"),
        repeat_scope=repeat_scope,
    )


def _expand_call_node(
    node: CallNode,
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
    elapsed = _expand_nodes(
        node.body,
        start_beat=start_beat,
        duration_beats=duration_beats,
        bpm=bpm,
        ctx=ctx,
        events=events,
        controls=controls,
        scope=(*scope, ("call", node.id)),
        repeat_scope=repeat_scope,
    )
    return elapsed if elapsed > 0 else node.body_beats


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
    required_functions = (
        "synth_render_serialized_plan_wav",
        "synth_play_serialized_plan",
        "synth_play_wav_bytes",
        "synth_render_plan_wav",
        "synth_render_event_wav",
        "synth_sample_duration",
    )
    if not all(callable(getattr(runtime, name, None)) for name in required_functions):
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
