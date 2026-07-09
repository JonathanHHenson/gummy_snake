"""Source-defined Sonic Pi synth from design files: :pnoise_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "pnoise_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def pnoise_gated(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 0.35, "cutoff": 110, "sustain": 0.25},
        **opts,
    ).layer("pnoise")
    signal.output()


SYNTH_TRACK = pnoise_gated
