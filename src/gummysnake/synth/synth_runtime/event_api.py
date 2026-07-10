from __future__ import annotations

import contextlib
import functools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from gummysnake.exceptions import ArgumentValidationError
from gummysnake.synth.synth_runtime.builder_context import _current_builder, _next_node_id
from gummysnake.synth.synth_runtime.expressions import BoundExpression
from gummysnake.synth.synth_runtime.lazy_values import (
    Ring,
    SampleDurationExpression,
    ensure_expr,
)
from gummysnake.synth.synth_runtime.logical_nodes import (
    CallNode,
    ControlTarget,
    EventNode,
    LoopNode,
    NodeHandle,
    PlanNode,
    ThreadNode,
)
from gummysnake.synth.synth_runtime.physical_plan import PhysicalPlan
from gummysnake.synth.synth_runtime.runtime_foundation import (
    Expression,
    _BUILTIN_SAMPLE_EXTENSIONS,
    _BUILTIN_SAMPLE_PACKAGE_DIR,
    SynthPlanError,
)
from gummysnake.synth.synth_runtime.scales_and_specs import (
    _FX_DEFINITIONS,
    _SYNTH_DEFINITIONS,
    FxHandle,
    _transposed_synth_note,
)

if TYPE_CHECKING:
    from gummysnake.synth.synth_runtime.context_managers import ThreadContext
    from gummysnake.synth.synth_runtime.definitions import FxDefinition, SynthDefinition


def thread(*, name: str | None = None) -> ThreadContext:
    """Record a nested logical block that starts in parallel with following code."""

    from gummysnake.synth.synth_runtime.context_managers import ThreadContext

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


def _fx_definition_key(name: str) -> str:
    return name.strip().removeprefix(":")


@dataclass(frozen=True, slots=True)
class CompiledSynthDefinition:
    """Bundled source-defined synth template loaded from a compiled ``.gss`` asset."""

    name: str
    path: Path

    def load_plan(self) -> PhysicalPlan:
        return PhysicalPlan.load(self.path)


@dataclass(frozen=True, slots=True)
class CompiledFxDefinition:
    """Bundled source-defined FX template loaded from a compiled ``.gsfx`` asset."""

    name: str
    path: Path

    def load_plan(self) -> PhysicalPlan:
        return PhysicalPlan.load(self.path)

    def build_chain(self, source_id: int, opts: Mapping[str, object]) -> tuple[FxHandle, ...]:
        plan = self.load_plan()
        if not plan.events or not plan.events[0].fx_chain:
            raise SynthPlanError(f"Compiled FX asset {self.name!r} does not contain an FX chain.")
        expanded: list[FxHandle] = []
        for handle in plan.events[0].fx_chain:
            merged_opts = dict(handle.opts)
            merged_opts.update(dict(opts))
            expanded.append(FxHandle(source_id, handle.name, merged_opts))
        return tuple(expanded)


_COMPILED_SYNTH_DEFINITIONS: dict[str, CompiledSynthDefinition] = {}
_COMPILED_FX_DEFINITIONS: dict[str, CompiledFxDefinition] = {}


def _compiled_synth_definition(name: str) -> CompiledSynthDefinition | None:
    key = _synth_definition_key(name)
    if key in _COMPILED_SYNTH_DEFINITIONS:
        return _COMPILED_SYNTH_DEFINITIONS[key]
    with contextlib.suppress(ArgumentValidationError):
        from gummysnake.synth.synth_runtime.track import builtin_synth_path

        definition = CompiledSynthDefinition(key, builtin_synth_path(key))
        _COMPILED_SYNTH_DEFINITIONS[key] = definition
        return definition
    return None


def _compiled_fx_definition(name: str) -> CompiledFxDefinition | None:
    key = _fx_definition_key(name)
    if key in _COMPILED_FX_DEFINITIONS:
        return _COMPILED_FX_DEFINITIONS[key]
    with contextlib.suppress(ArgumentValidationError):
        from gummysnake.synth.synth_runtime.track import builtin_fx_path

        definition = CompiledFxDefinition(key, builtin_fx_path(key))
        _COMPILED_FX_DEFINITIONS[key] = definition
        return definition
    return None


def _lookup_synth_definition(name: str) -> SynthDefinition | CompiledSynthDefinition | None:
    key = _synth_definition_key(name)
    if key.startswith("_"):
        return None
    definition = _SYNTH_DEFINITIONS.get(key)
    if definition is not None:
        return definition
    return _compiled_synth_definition(key)


def _lookup_fx_definition(name: str) -> FxDefinition | CompiledFxDefinition | None:
    key = _fx_definition_key(name)
    if key.startswith("_"):
        return None
    definition = _FX_DEFINITIONS.get(key)
    if definition is not None:
        return definition
    return _compiled_fx_definition(key)


def _expand_fx_handle(handle: FxHandle) -> tuple[FxHandle, ...]:
    definition = _lookup_fx_definition(handle.name)
    if definition is None:
        if handle.name.startswith("_"):
            return (handle,)
        raise ArgumentValidationError(f"No bundled compiled FX asset named {handle.name!r}.")
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
