from __future__ import annotations

import builtins
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, cast

from gummysnake.exceptions import ArgumentValidationError
from gummysnake.synth.synth_runtime.lazy_values import (
    Expression,
    MusicExpression,
    Ring,
    ensure_expr,
)
from gummysnake.synth.synth_runtime.pattern_helpers import (
    _CHORD_INTERVALS,
    _SCALE_INTERVALS,
    note,
)


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

        from gummysnake.synth.synth_runtime.context_managers import synth_output

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
