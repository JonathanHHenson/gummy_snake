"""Source-defined Sonic Pi synth from design files: :chiplead."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.src._common import synth_duration

SYNTH_NAME = "chiplead"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def chiplead(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.25, "cutoff": 125, "pulse_width": 0.25},
            **opts,
        )
        .layer("square", amp=0.65)
        .layer("square", transpose=12, amp=0.25)
    )
    signal.output()


SYNTH_TRACK = chiplead
