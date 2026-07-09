"""Source-defined Sonic Pi synth from design files: :chipnoise_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.src._common import synth_duration

SYNTH_NAME = "chipnoise_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def chipnoise_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.2, "cutoff": 115, "sustain": 0.25},
            **opts,
        )
        .layer("cnoise", amp=0.7)
        .layer("noise", amp=0.2)
    )
    signal.output()


SYNTH_TRACK = chipnoise_gated
