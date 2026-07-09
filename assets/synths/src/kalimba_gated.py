"""Source-defined Sonic Pi synth from design files: :kalimba_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "kalimba_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def kalimba_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 120, "sustain": 0.25},
            **opts,
        )
        .layer("sine", amp=0.75)
        .layer("sine", transpose=12.01, amp=0.32)
        .layer("sine", transpose=19.02, amp=0.18)
        .layer("cnoise", amp=0.05)
    )
    signal.output()


SYNTH_TRACK = kalimba_gated
