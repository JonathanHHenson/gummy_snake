from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from gummysnake.synth.synth_runtime.values.foundation import Expression
from gummysnake.synth.synth_runtime.values.scales_and_specs import FxHandle


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
        from gummysnake.synth.synth_runtime.playback_export.track import _append_node_explain

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
    order: int = 0


@dataclass(frozen=True, slots=True)
class ScheduledControl:
    """Concrete control change in a physical plan."""

    target_instance: tuple[object, ...]
    target_id: int
    time_seconds: float
    opts: Mapping[str, object]
    order: int = 0
