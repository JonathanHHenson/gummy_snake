"""Source-defined Sonic Pi synth from design files: :cnoise."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.src._common import synth_duration

SYNTH_NAME = "cnoise"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def cnoise(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 0.35, "cutoff": 110},
        **opts,
    ).layer("cnoise")
    signal.output()


SYNTH_TRACK = cnoise
