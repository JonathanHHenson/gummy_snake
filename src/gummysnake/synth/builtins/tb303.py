"""Source-defined Sonic Pi synth from design files: :tb303."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "tb303"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def tb303(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 90, "res": 0.85},
            **opts,
        )
        .layer("saw", amp=0.75)
        .layer("square", amp=0.2)
    )
    signal.output()


SYNTH_TRACK = tb303
