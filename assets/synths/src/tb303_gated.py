"""Source-defined Sonic Pi synth from design files: :tb303_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "tb303_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def tb303_gated(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={
            "attack": 0.01,
            "decay": 0,
            "sustain": 0,
            "release": 1,
            "attack_level": 1,
            "decay_level": 1,
            "sustain_level": 1,
            "env_curve": 1,
            "cutoff": 120,
            "cutoff_min": 30,
            "cutoff_attack": -1,
            "cutoff_decay": -1,
            "cutoff_sustain": -1,
            "cutoff_release": -1,
            "cutoff_attack_level": 1,
            "cutoff_decay_level": -1,
            "cutoff_sustain_level": 1,
            "cutoff_env_curve": 2,
            "res": 0.9,
            "pulse_width": 0.5,
            "amp_fudge": 1,
        },
        **opts,
    ).layer("saw")
    signal.output()


SYNTH_TRACK = tb303_gated
