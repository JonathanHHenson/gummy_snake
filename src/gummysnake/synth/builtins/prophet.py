"""Source-defined Sonic Pi synth from design files: :prophet."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "prophet"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def prophet(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={
                "attack": 0.01,
                "decay": 0,
                "sustain": 0,
                "release": 1,
                "attack_level": 1,
                "sustain_level": 1,
                "env_curve": 1,
                "cutoff": 110,
                "res": 0.7,
                "amp_fudge": 1.5,
                "pre_shape_normalise": True,
                "pre_shape_level": 1,
                "pre_filter_shape": "squared",
            },
            **opts,
        )
        .layer(
            "pulse",
            amp=0.28,
            pulse_width=0.27,
            pulse_width_lfo_rate=1,
            pulse_width_lfo_depth=0.23,
            pulse_width_lfo_wave=3,
        )
        .layer(
            "pulse",
            amp=0.28,
            pulse_width=0.76,
            pulse_width_lfo_rate=0.3,
            pulse_width_lfo_depth=0.24,
            pulse_width_lfo_wave=3,
        )
        .layer(
            "pulse",
            amp=0.28,
            pulse_width=0.48,
            pulse_width_lfo_rate=0.4,
            pulse_width_lfo_depth=0.4,
            pulse_width_lfo_wave=2,
        )
        .layer(
            "pulse",
            amp=0.28,
            pulse_width=0.48,
            pulse_width_lfo_rate=0.4,
            pulse_width_lfo_phase=0.19,
            pulse_width_lfo_depth=0.4,
            pulse_width_lfo_wave=2,
        )
        .layer(
            "pulse",
            transpose=-12,
            amp=0.14,
            pulse_width=0.48,
            pulse_width_lfo_rate=2,
            pulse_width_lfo_depth=0.4,
            pulse_width_lfo_wave=2,
        )
    )
    signal.output()


SYNTH_TRACK = prophet
