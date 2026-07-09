"""Source-defined Sonic Pi synth from design files: :piano_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "piano_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def piano_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 120, "sustain": 0.25},
            **opts,
        )
        .layer("sine", amp=0.7)
        .layer("sine", transpose=12.02, amp=0.3)
        .layer("sine", transpose=19.03, amp=0.16)
        .layer("cnoise", amp=0.08)
    )
    signal.output()


SYNTH_TRACK = piano_gated
