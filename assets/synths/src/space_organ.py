"""Source-defined Sonic Pi synth from design files: :space_organ."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "space_organ"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def space_organ(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 1.2, "cutoff": 115},
            **opts,
        )
        .layer("sine", transpose=-12, amp=0.25)
        .layer("sine", amp=0.5)
        .layer("tri", transpose=7, amp=0.2)
        .layer("square", transpose=12, amp=0.12)
    )
    signal.output()


SYNTH_TRACK = space_organ
