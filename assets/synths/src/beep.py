"""Source-defined Sonic Pi synth from design files: :beep."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.src._common import synth_duration

SYNTH_NAME = "beep"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def beep(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 1, "env_curve": 1},
        **opts,
    ).layer("sine")
    signal.output()


SYNTH_TRACK = beep
