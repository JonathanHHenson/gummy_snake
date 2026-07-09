"""Source-defined Sonic Pi synth from design files: :fm_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "fm_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def fm_gated(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 0.35, "divisor": 2, "depth": 1.2, "cutoff": 100, "sustain": 0.25},
        **opts,
    ).layer("fm")
    signal.output()


SYNTH_TRACK = fm_gated
