"""Source-defined Sonic Pi synth from design files: :prophet_gated."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "prophet_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def prophet_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 110, "res": 0.7, "sustain": 0.25},
            **opts,
        )
        .layer("square", transpose=-12, amp=0.35)
        .layer("square", transpose=-0.07, amp=0.35)
        .layer("square", transpose=0.11, amp=0.35)
    )
    signal.output()


SYNTH_TRACK = prophet_gated
