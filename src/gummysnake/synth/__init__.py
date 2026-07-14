"""Pythonic logical-track synth API for Gummy Snake.

The synth package lets sketches build deterministic logical plans with
``@sy.track`` functions and reusable source-defined synths with ``@sy.synth``.
Plans can then be expanded into a physical event plan that is rendered by the
required Rust ``gummysnake.rust._canvas`` runtime, saved, played through the
existing ``Sound`` playback facade, or converted to a ``gummysnake.Sound``.

This module intentionally excludes browser APIs and leaves live loops, MIDI,
OSC, live audio input, sound output routing, and Minecraft integration for future
runtime-backed extensions.
"""

from __future__ import annotations

from typing import Any

from gummysnake.synth.synth_runtime.composition.context_managers import (
    fx,
    fx_input,
    fx_output,
    loop,
    synth,
    synth_input,
    synth_output,
    use_synth,
)
from gummysnake.synth.synth_runtime.composition.definitions import (
    FxDefinition,
    SynthDefinition,
    TrackDefinition,
)
from gummysnake.synth.synth_runtime.composition.event_api import (
    control,
    play,
    sample,
    sample_duration,
    sleep,
    thread,
    when,
)
from gummysnake.synth.synth_runtime.composition.logical_nodes import NodeHandle, TrackPlan
from gummysnake.synth.synth_runtime.composition.track_decorator import track
from gummysnake.synth.synth_runtime.physical.execution import (
    SynthRuntimeDiagnostics,
    WorkerCount,
    configure_workers,
    reset_synth_diagnostics,
    synth_diagnostics,
)
from gummysnake.synth.synth_runtime.physical.physical_plan import PhysicalPlan
from gummysnake.synth.synth_runtime.playback_export.playback import TrackPlayback
from gummysnake.synth.synth_runtime.playback_export.track import (
    Track,
    builtin_fx_names,
    builtin_fx_path,
    builtin_synth_names,
    builtin_synth_path,
    load_builtin_fx_plan,
    load_builtin_synth_plan,
    load_physical_plan,
)
from gummysnake.synth.synth_runtime.values.foundation import (
    Duration,
    Format,
    SynthPlanError,
    duration,
)
from gummysnake.synth.synth_runtime.values.lazy_values import Ring, ring
from gummysnake.synth.synth_runtime.values.pattern_helpers import (
    bools,
    choose,
    chord,
    dice,
    knit,
    line,
    look,
    note,
    note_frequency,
    octs,
    one_in,
    rand,
    rand_i,
    range,
    rrand,
    rrand_i,
    scale,
    spread,
    tick,
)
from gummysnake.synth.synth_runtime.values.scales_and_specs import (
    FxHandle,
    FxSignal,
    SynthSignal,
)


def __getattr__(name: str) -> Any:
    """Return dynamically registered track or synth definitions.

    ``@sy.track`` and ``@sy.synth`` register decorated functions on this module
    so tracks can call reusable definitions as ``sy.some_track(...)`` or select
    source-defined synths by name. Static analyzers see unknown names as ``Any``
    while runtime still raises ``AttributeError`` for truly missing names.
    """

    raise AttributeError(f"module 'gummysnake.synth' has no attribute {name!r}")


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
    "SynthRuntimeDiagnostics",
    "SynthSignal",
    "Track",
    "TrackDefinition",
    "TrackPlan",
    "TrackPlayback",
    "WorkerCount",
    "bools",
    "builtin_fx_names",
    "builtin_fx_path",
    "builtin_synth_names",
    "builtin_synth_path",
    "chord",
    "choose",
    "configure_workers",
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
    "reset_synth_diagnostics",
    "ring",
    "rrand",
    "rrand_i",
    "sample",
    "sample_duration",
    "scale",
    "sleep",
    "spread",
    "synth",
    "synth_diagnostics",
    "synth_input",
    "synth_output",
    "thread",
    "tick",
    "track",
    "use_synth",
    "when",
]
