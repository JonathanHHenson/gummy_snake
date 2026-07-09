"""Source-defined Sonic Pi synth from design files: :hoover_gated."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "hoover_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def hoover_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 130, "sustain": 0.25},
            **opts,
        )
        .layer("saw", transpose=-12, amp=0.35)
        .layer("saw", transpose=-0.12, amp=0.35)
        .layer("saw", transpose=0.12, amp=0.35)
        .layer("pulse", transpose=0.31, amp=0.25)
    )
    signal.output()


SYNTH_TRACK = hoover_gated
