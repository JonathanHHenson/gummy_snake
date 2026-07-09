"""Source-defined Sonic Pi synth from design files: :chiplead_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "chiplead_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def chiplead_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.25, "cutoff": 125, "pulse_width": 0.25, "sustain": 0.25},
            **opts,
        )
        .layer("square", amp=0.65)
        .layer("square", transpose=12, amp=0.25)
    )
    signal.output()


SYNTH_TRACK = chiplead_gated
