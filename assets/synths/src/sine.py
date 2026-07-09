"""Source-defined Sonic Pi synth from design files: :sine."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "sine"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sine(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 1, "env_curve": 1},
        **opts,
    ).layer("sine")
    signal.output()


SYNTH_TRACK = sine
