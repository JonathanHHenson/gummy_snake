"""Source-defined Sonic Pi synth from design files: :square_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "square_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def square_gated(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 0.35, "cutoff": 100, "sustain": 0.25},
        **opts,
    ).layer("square")
    signal.output()


SYNTH_TRACK = square_gated
