"""Source-defined Sonic Pi synth from design files: :supersaw_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "supersaw_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def supersaw_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 130, "sustain": 0.25},
            **opts,
        )
        .layer("saw", transpose=-0.18, amp=0.2)
        .layer("saw", transpose=-0.11, amp=0.2)
        .layer("saw", transpose=-0.05, amp=0.2)
        .layer("saw", amp=0.25)
        .layer("saw", transpose=0.05, amp=0.2)
        .layer("saw", transpose=0.11, amp=0.2)
        .layer("saw", transpose=0.18, amp=0.2)
    )
    signal.output()


SYNTH_TRACK = supersaw_gated
