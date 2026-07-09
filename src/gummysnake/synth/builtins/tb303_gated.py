"""Source-defined Sonic Pi synth from design files: :tb303_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "tb303_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def tb303_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 90, "res": 0.85, "sustain": 0.25},
            **opts,
        )
        .layer("saw", amp=0.75)
        .layer("square", amp=0.2)
    )
    signal.output()


SYNTH_TRACK = tb303_gated
