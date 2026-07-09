"""Source-defined Sonic Pi synth from design files: :rodeo_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "rodeo_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def rodeo_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 105, "pulse_width": 0.35, "sustain": 0.25},
            **opts,
        )
        .layer("pulse", amp=0.55)
        .layer("pulse", transpose=12, amp=0.25)
        .layer("saw", transpose=-12, amp=0.2)
    )
    signal.output()


SYNTH_TRACK = rodeo_gated
