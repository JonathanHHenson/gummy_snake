"""Source-defined Sonic Pi synth from design files: :growl_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "growl_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def growl_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 80, "res": 0.7, "sustain": 0.25},
            **opts,
        )
        .layer("saw", amp=0.55)
        .layer("square", transpose=-12, amp=0.35)
        .layer("sine", transpose=12, amp=0.12)
    )
    signal.output()


SYNTH_TRACK = growl_gated
