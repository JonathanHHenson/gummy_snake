"""Source-defined Sonic Pi synth from design files: :bass_foundation_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "bass_foundation_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def bass_foundation_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 80, "res": 0.4, "sustain": 0.25},
            **opts,
        )
        .layer("saw", transpose=-12, amp=0.65)
        .layer("sine", transpose=-24, amp=0.25)
    )
    signal.output()


SYNTH_TRACK = bass_foundation_gated
