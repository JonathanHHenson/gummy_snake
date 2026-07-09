"""Source-defined Sonic Pi synth from design files: :sc808_maracas."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "sc808_maracas"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_maracas(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.16, "cutoff": 125},
            **opts,
        )
        .layer("cnoise", amp=0.85)
        .layer("noise", amp=0.25)
    )
    signal.output()


SYNTH_TRACK = sc808_maracas
