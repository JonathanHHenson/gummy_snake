"""Source-defined Sonic Pi synth from design files: :mod_fm_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.srcmon import synth_duration

SYNTH_NAME = "mod_fm_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def mod_fm_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "divisor": 2, "depth": 1.2, "cutoff": 100, "sustain": 0.25},
            **opts,
        )
        .layer("fm", amp=0.55)
        .layer("fm", transpose=7, amp=0.35)
    )
    signal.output()


SYNTH_TRACK = mod_fm_gated
