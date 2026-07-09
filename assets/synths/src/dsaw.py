"""Source-defined Sonic Pi synth from design files: :dsaw."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.src._common import synth_duration

SYNTH_NAME = "dsaw"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dsaw(note: object = 60, **opts: object) -> None:
    detune = opts.pop("detune", 0.1)
    signal = (
        sy.synth_input(
            note,
            defaults={
                "release": 1,
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


SYNTH_TRACK = dsaw
