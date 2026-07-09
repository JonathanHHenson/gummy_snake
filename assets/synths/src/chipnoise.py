"""Source-defined Sonic Pi synth from design files: :chipnoise."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "chipnoise"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def chipnoise(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.2, "cutoff": 115},
            **opts,
        )
        .layer("cnoise", amp=0.7)
        .layer("noise", amp=0.2)
    )
    signal.output()


SYNTH_TRACK = chipnoise
