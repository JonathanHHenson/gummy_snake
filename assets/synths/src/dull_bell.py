"""Source-defined Sonic Pi synth from design files: :dull_bell."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.srcmon import synth_duration

SYNTH_NAME = "dull_bell"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dull_bell(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 1.0},
            **opts,
        )
        .layer("sine", amp=0.8)
        .layer("sine", transpose=6.7, amp=0.35)
        .layer("sine", transpose=12.9, amp=0.22)
    )
    signal.output()


SYNTH_TRACK = dull_bell
