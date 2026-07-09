"""Source-defined Sonic Pi synth from design files: :bnoise_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "bnoise_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def bnoise_gated(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 0.35, "cutoff": 110, "sustain": 0.25},
        **opts,
    ).layer("bnoise")
    signal.output()


SYNTH_TRACK = bnoise_gated
