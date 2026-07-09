"""Source-defined Sonic Pi synth from design files: :saw_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "saw_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def saw_gated(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 0.35, "cutoff": 100, "sustain": 0.25},
        **opts,
    ).layer("saw")
    signal.output()


SYNTH_TRACK = saw_gated
