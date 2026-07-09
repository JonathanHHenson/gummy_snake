"""Source-defined Sonic Pi synth from design files: :pulse_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "pulse_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def pulse_gated(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={
            "release": 1,
            "sustain": 0,
            "env_curve": 1,
            "cutoff": 100,
            "pulse_width": 0.5,
            "amp_fudge": 0.8,
            "normalise": True,
        },
        **opts,
    ).layer("pulse")
    signal.output()


SYNTH_TRACK = pulse_gated
