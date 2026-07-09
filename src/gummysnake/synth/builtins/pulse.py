"""Source-defined Sonic Pi synth from design files: :pulse."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "pulse"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def pulse(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 0.35, "cutoff": 100, "pulse_width": 0.5},
        **opts,
    ).layer("pulse")
    signal.output()


SYNTH_TRACK = pulse
