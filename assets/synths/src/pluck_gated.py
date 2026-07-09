"""Source-defined Sonic Pi synth from design files: :pluck_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "pluck_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def pluck_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 120, "sustain": 0.25},
            **opts,
        )
        .layer("tri", amp=0.65)
        .layer("pnoise", amp=0.25)
    )
    signal.output()


SYNTH_TRACK = pluck_gated
