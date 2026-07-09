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

from gummysnake.synth.core import (
    Duration,
    Format,
    FxDefinition,
    FxHandle,
    FxSignal,
    NodeHandle,
    PhysicalPlan,
    Ring,
    SynthDefinition,
    SynthPlanError,
    SynthSignal,
    Track,
    TrackDefinition,
    TrackInstance,
    TrackPlan,
    TrackPlayback,
    bools,
    builtin_fx_names,
    builtin_fx_path,
    builtin_synth_names,
    builtin_synth_path,
    choose,
    chord,
    control,
    dice,
    duration,
    fx,
    fx_input,
    fx_output,
    knit,
    line,
    load_builtin_fx_plan,
    load_builtin_synth_plan,
    load_physical_plan,
    look,
    loop,
    note,
    note_frequency,
    octs,
    one_in,
    play,
    rand,
    rand_i,
    range,
    ring,
    rrand,
    rrand_i,
    sample,
    sample_duration,
    scale,
    sleep,
    spread,
    synth,
    synth_input,
    synth_output,
    thread,
    tick,
    track,
    use_synth,
    when,
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
