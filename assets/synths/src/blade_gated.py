"""Source-defined Sonic Pi synth from design files: :blade_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.src._common import synth_duration

SYNTH_NAME = "blade_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def blade_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 100, "sustain": 0.25},
            **opts,
        )
        .layer("saw", transpose=-0.08, amp=0.45)
        .layer("saw", transpose=0.08, amp=0.45)
        .layer("sine", transpose=12, amp=0.15)
    )
    signal.output()


SYNTH_TRACK = blade_gated
