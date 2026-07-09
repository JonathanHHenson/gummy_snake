"""Source-defined Sonic Pi synth from design files: :tri."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "tri"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def tri(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={
            "release": 1,
            "env_curve": 1,
            "cutoff": 100,
            "amp_fudge": 1.4,
            "normalise": True,
        },
        **opts,
    ).layer("tri")
    signal.output()


SYNTH_TRACK = tri
