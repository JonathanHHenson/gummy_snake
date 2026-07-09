"""Source-defined Sonic Pi synth from design files: :zawa_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "zawa_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def zawa_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 100, "res": 0.8, "sustain": 0.25},
            **opts,
        )
        .layer("saw", amp=0.6)
        .layer("saw", transpose=12, amp=0.25)
        .layer("saw", transpose=24, amp=0.15)
    )
    signal.output()


SYNTH_TRACK = zawa_gated
