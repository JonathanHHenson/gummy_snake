"""Source-defined Sonic Pi synth from design files: :hollow."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "hollow"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def hollow(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.9, "cutoff": 90, "res": 0.8},
            **opts,
        )
        .layer("bnoise", amp=0.65)
        .layer("sine", amp=0.25)
    )
    signal.output()


SYNTH_TRACK = hollow
