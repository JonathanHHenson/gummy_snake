"""Source-defined Sonic Pi synth from design files: :bnoise."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.srcmon import synth_duration

SYNTH_NAME = "bnoise"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def bnoise(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 0.35, "cutoff": 110},
        **opts,
    ).layer("bnoise")
    signal.output()


SYNTH_TRACK = bnoise
