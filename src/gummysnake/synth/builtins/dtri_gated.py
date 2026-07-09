"""Source-defined Sonic Pi synth from design files: :dtri_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "dtri_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dtri_gated(note: object = 60, **opts: object) -> None:
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
        .layer("tri")
        .layer("tri", transpose=detune)
    )
    signal.output()


SYNTH_TRACK = dtri_gated
