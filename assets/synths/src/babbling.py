"""Source-defined Sonic Pi synth from design files: :babbling."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.srcmon import synth_duration

SYNTH_NAME = "babbling"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def babbling(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.6, "cutoff": 100},
            **opts,
        )
        .layer("pnoise", amp=0.45)
        .layer("sine", transpose=7, amp=0.25)
        .layer("sine", transpose=12, amp=0.2)
    )
    signal.output()


SYNTH_TRACK = babbling
