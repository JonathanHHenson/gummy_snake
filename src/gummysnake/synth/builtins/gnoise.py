"""Source-defined Sonic Pi synth from design files: :gnoise."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "gnoise"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def gnoise(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 0.35, "cutoff": 110},
        **opts,
    ).layer("gnoise")
    signal.output()


SYNTH_TRACK = gnoise
