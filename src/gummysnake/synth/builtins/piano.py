"""Source-defined Sonic Pi synth from design files: :piano."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "piano"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def piano(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 1.1, "cutoff": 120},
            **opts,
        )
        .layer("sine", amp=0.7)
        .layer("sine", transpose=12.02, amp=0.3)
        .layer("sine", transpose=19.03, amp=0.16)
        .layer("cnoise", amp=0.08)
    )
    signal.output()


SYNTH_TRACK = piano
