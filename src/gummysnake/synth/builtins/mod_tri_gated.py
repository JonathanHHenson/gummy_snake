"""Source-defined Sonic Pi synth from design files: :mod_tri_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "mod_tri_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def mod_tri_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 100, "sustain": 0.25},
            **opts,
        )
        .layer("tri", amp=0.55)
        .layer("tri", transpose=7, amp=0.35)
    )
    signal.output()


SYNTH_TRACK = mod_tri_gated
