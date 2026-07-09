"""Source-defined Sonic Pi synth from design files: :sc808_open_hihat."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "sc808_open_hihat"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_open_hihat(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.45, "cutoff": 127},
            **opts,
        )
        .layer("cnoise", amp=0.75)
        .layer("gnoise", amp=0.3)
    )
    signal.output()


SYNTH_TRACK = sc808_open_hihat
