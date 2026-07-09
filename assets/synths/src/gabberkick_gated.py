"""Source-defined Sonic Pi synth from design files: :gabberkick_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "gabberkick_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def gabberkick_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 95, "res": 0.4, "sustain": 0.25},
            **opts,
        )
        .layer("sine", transpose=-26, amp=0.95)
        .layer("sine", transpose=-14, amp=0.35)
        .layer("cnoise", amp=0.08)
    )
    signal.output()


SYNTH_TRACK = gabberkick_gated
