from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from gummysnake.assets.sound import CanvasSound, Sound
from gummysnake.exceptions import ArgumentValidationError
from gummysnake.synth.synth_runtime.composition.logical_nodes import (
    BindNode,
    CallNode,
    ControlNode,
    EventNode,
    LoopNode,
    PlanNode,
    SleepNode,
    ThreadNode,
    TrackPlan,
)
from gummysnake.synth.synth_runtime.physical.physical_plan import PhysicalPlan
from gummysnake.synth.synth_runtime.physical.rendering import (
    _beats_to_seconds,
    _compile_physical_plan,
    _expand_physical_plan,
    _render_physical_plan,
    _render_physical_plan_to_file,
    _write_wav_file,
)
from gummysnake.synth.synth_runtime.playback_export.playback import (
    TrackPlayback,
    _RenderedTrackCacheEntry,
)
from gummysnake.synth.synth_runtime.playback_export.samples_and_export import (
    _resolve_format,
    _wav_duration_seconds,
    _write_mp3_with_ffmpeg,
)
from gummysnake.synth.synth_runtime.values.foundation import (
    _BUILTIN_FX_COMPILED_DIR,
    _BUILTIN_SYNTH_COMPILED_DIR,
    _SAMPLE_RATE,
    Duration,
    Format,
)

if TYPE_CHECKING:
    from gummysnake.synth.synth_runtime.composition.definitions import (
        FxDefinition,
        SynthDefinition,
        TrackDefinition,
    )


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
        if (cached := self._render_cache.get(cache_key)) and cached.payload is not None:
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
        format: Format | str | None = None,
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
        cache_key = (duration_seconds, int(sample_rate))
        if resolved_format == Format.WAV:
            if cached := self._render_cache.get(cache_key):
                if cached.payload is not None:
                    _write_wav_file(cached.payload, output_path)
                    cached.path = output_path
                    return output_path
                if cached.path == output_path and output_path.exists():
                    return output_path
            plan = _expand_physical_plan(self.logical_plan, duration_seconds)
            _render_physical_plan_to_file(plan, output_path, sample_rate=sample_rate)
            self._render_cache[cache_key] = _RenderedTrackCacheEntry(
                None, duration_seconds, output_path
            )
            return output_path
        wav_payload = self.render(duration_seconds, sample_rate=sample_rate)
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

        output_path = Path(path)
        duration_seconds = _duration_seconds_or_default(duration, self)
        plan = _expand_physical_plan(self.logical_plan, duration_seconds)
        rust_asset = _compile_physical_plan(plan, sample_rate=sample_rate).render_sound(
            str(output_path)
        )
        rust_sound = CanvasSound.from_rust(rust_asset)
        return Sound(rust_sound, path=output_path, rust_sound=rust_sound)

    def play(
        self,
        *,
        duration: Duration | float | None = None,
        sample_rate: int = _SAMPLE_RATE,
        realtime: bool = True,
        look_ahead: float = 0.05,
    ) -> TrackPlayback | Sound:
        """Start playback and return a handle.

        Realtime playback compiles one Rust-owned physical program and starts a
        voice on the process-local SDL mixer. Open tracks repeat that native
        program without Python horizon expansion. Call ``wait_until_stop()`` on
        finite playback to block until it finishes.
        """

        if not realtime:
            rendered = self.to_sound(duration=duration, sample_rate=sample_rate)
            rendered.play()
            return rendered
        rolling = duration is None and _should_play_as_rolling_loop(self.logical_plan)
        duration_seconds = _duration_seconds_or_default(duration, self)
        playback = TrackPlayback(
            _expand_physical_plan(self.logical_plan, duration_seconds),
            sample_rate=sample_rate,
            look_ahead=look_ahead,
            name=self.logical_plan.name,
            rolling=rolling,
            rendered_cache=self._render_cache.get((duration_seconds, int(sample_rate))),
        )
        return playback.start()


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
    """Return bundled compiled FX names available under ``assets/fx/compiled``."""

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
