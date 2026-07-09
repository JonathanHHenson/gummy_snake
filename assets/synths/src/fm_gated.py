"""Source-defined Sonic Pi synth from design files: :fm_gated."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "fm_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def fm_gated(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={
            "release": 1,
            "sustain": 0,
            "env_curve": 1,
            "divisor": 2,
            "depth": 1.0,
            "cutoff": 100,
            "amp_fudge": 0.8,
        },
        **opts,
    ).layer("fm")
    signal.output()


SYNTH_TRACK = fm_gated
