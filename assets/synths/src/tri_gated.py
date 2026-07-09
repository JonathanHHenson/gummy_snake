"""Source-defined Sonic Pi synth from design files: :tri_gated."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "tri_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def tri_gated(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={
            "release": 1,
            "sustain": 0,
            "env_curve": 1,
            "cutoff": 100,
            "amp_fudge": 1.4,
            "normalise": True,
        },
        **opts,
    ).layer("tri")
    signal.output()


SYNTH_TRACK = tri_gated
