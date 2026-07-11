"""Synth runtime compatibility module.

Helper modules keep this public module path stable while each runtime chunk remains
normally importable on its own.
"""

from __future__ import annotations

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
from gummysnake.synth.synth_runtime.physical.physical_plan import PhysicalPlan
from gummysnake.synth.synth_runtime.playback_export.playback import TrackPlayback
from gummysnake.synth.synth_runtime.playback_export.track import (
    Track,
    TrackInstance,
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
