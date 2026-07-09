"""Source-defined Sonic Pi synth from design files: :woah."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "woah"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def woah(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.6, "cutoff": 90, "res": 0.6},
            **opts,
        )
        .layer("saw", amp=0.55)
        .layer("pulse", transpose=12, amp=0.3)
    )
    signal.output()


SYNTH_TRACK = woah
