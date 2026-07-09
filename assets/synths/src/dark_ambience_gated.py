"""Source-defined Sonic Pi synth from design files: :dark_ambience_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "dark_ambience_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dark_ambience_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 100, "sustain": 0.25},
            **opts,
        )
        .layer("sine", amp=0.35)
        .layer("tri", transpose=12, amp=0.25)
        .layer("saw", transpose=24, amp=0.15)
        .layer("pnoise", amp=0.12)
    )
    signal.output()


SYNTH_TRACK = dark_ambience_gated
