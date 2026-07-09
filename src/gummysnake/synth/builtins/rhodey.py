"""Source-defined Sonic Pi synth from design files: :rhodey."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "rhodey"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def rhodey(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 1.0, "divisor": 2.01, "depth": 2.5, "cutoff": 120},
            **opts,
        )
        .layer("fm", amp=0.55)
        .layer("sine", transpose=12, amp=0.2)
        .layer("tri", transpose=19, amp=0.15)
    )
    signal.output()


SYNTH_TRACK = rhodey
