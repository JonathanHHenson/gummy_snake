"""Source-defined Sonic Pi synth from design files: :saw."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "saw"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def saw(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={
            "release": 1,
            "env_curve": 1,
            "cutoff": 100,
            "amp_fudge": 0.8,
            "normalise": True,
        },
        **opts,
    ).layer("saw")
    signal.output()


SYNTH_TRACK = saw
