"""Source-defined Sonic Pi synth from design files: :dsaw_gated."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "dsaw_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dsaw_gated(note: object = 60, **opts: object) -> None:
    detune = opts.pop("detune", 0.1)
    signal = (
        sy.synth_input(
            note,
            defaults={
                "release": 1,
                "sustain": 0,
                "env_curve": 1,
                "cutoff": 100,
                "amp_fudge": 1.1,
                "normalise": True,
            },
            **opts,
        )
        .layer("saw")
        .layer("saw", transpose=detune)
    )
    signal.output()


SYNTH_TRACK = dsaw_gated
