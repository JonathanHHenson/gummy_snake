"""Source-defined Sonic Pi synth from design files: :bass_highend_gated."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "bass_highend_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def bass_highend_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 90, "res": 0.45, "sustain": 0.25},
            **opts,
        )
        .layer("saw", transpose=-24, amp=0.45)
        .layer("saw", amp=0.45)
        .layer("saw", transpose=7, amp=0.25)
    )
    signal.output()


SYNTH_TRACK = bass_highend_gated
