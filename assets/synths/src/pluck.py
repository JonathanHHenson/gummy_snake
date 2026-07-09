"""Source-defined Sonic Pi synth from design files: :pluck."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "pluck"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def pluck(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 1.0, "cutoff": 120},
            **opts,
        )
        .layer("tri", amp=0.65)
        .layer("pnoise", amp=0.25)
    )
    signal.output()


SYNTH_TRACK = pluck
