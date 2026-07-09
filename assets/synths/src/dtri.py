"""Source-defined Sonic Pi synth from design files: :dtri."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "dtri"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dtri(note: object = 60, **opts: object) -> None:
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
        .layer("tri")
        .layer("tri", transpose=detune)
    )
    signal.output()


SYNTH_TRACK = dtri
