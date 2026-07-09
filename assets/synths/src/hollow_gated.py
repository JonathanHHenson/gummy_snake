"""Source-defined Sonic Pi synth from design files: :hollow_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "hollow_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def hollow_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 90, "res": 0.8, "sustain": 0.25},
            **opts,
        )
        .layer("bnoise", amp=0.65)
        .layer("sine", amp=0.25)
    )
    signal.output()


SYNTH_TRACK = hollow_gated
