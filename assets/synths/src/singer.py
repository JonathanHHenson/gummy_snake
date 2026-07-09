"""Source-defined Sonic Pi synth from design files: :singer."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "singer"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def singer(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.8, "cutoff": 95, "res": 0.5},
            **opts,
        )
        .layer("sine", amp=0.55)
        .layer("sine", transpose=12, amp=0.18)
        .layer("pnoise", amp=0.08)
    )
    signal.output()


SYNTH_TRACK = singer
