"""Source-defined Sonic Pi synth from design files: :arpeg-click."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "arpeg-click"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def arpeg_click(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.08, "cutoff": 115},
            **opts,
        )
        .layer("sine", amp=0.35)
        .layer("cnoise", amp=0.55)
    )
    signal.output()


SYNTH_TRACK = arpeg_click
