"""Source-defined Sonic Pi synth from design files: :dark_sea_horn."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "dark_sea_horn"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dark_sea_horn(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 1.2, "cutoff": 80, "res": 0.6},
            **opts,
        )
        .layer("sine", transpose=-12, amp=0.45)
        .layer("sine", amp=0.35)
        .layer("bnoise", amp=0.12)
    )
    signal.output()


SYNTH_TRACK = dark_sea_horn
