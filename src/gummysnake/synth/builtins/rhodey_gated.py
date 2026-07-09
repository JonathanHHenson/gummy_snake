"""Source-defined Sonic Pi synth from design files: :rhodey_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "rhodey_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def rhodey_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={
                "release": 0.35,
                "divisor": 2.01,
                "depth": 2.5,
                "cutoff": 120,
                "sustain": 0.25,
            },
            **opts,
        )
        .layer("fm", amp=0.55)
        .layer("sine", transpose=12, amp=0.2)
        .layer("tri", transpose=19, amp=0.15)
    )
    signal.output()


SYNTH_TRACK = rhodey_gated
