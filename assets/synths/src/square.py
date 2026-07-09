"""Source-defined Sonic Pi synth from design files: :square."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "square"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def square(note: object = 60, **opts: object) -> None:
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
    ).layer("square")
    signal.output()


SYNTH_TRACK = square
