"""Source-defined Sonic Pi synth from design files: :fm."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.src._common import synth_duration

SYNTH_NAME = "fm"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def fm(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={
            "release": 1,
            "env_curve": 1,
            "divisor": 2,
            "depth": 1.0,
            "cutoff": 100,
            "amp_fudge": 0.8,
        },
        **opts,
    ).layer("fm")
    signal.output()


SYNTH_TRACK = fm
