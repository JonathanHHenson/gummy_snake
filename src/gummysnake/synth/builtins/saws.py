"""Source-defined Sonic Pi synth from design files: :saws."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "saws"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def saws(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.45, "cutoff": 100},
            **opts,
        )
        .layer("saw", transpose=-0.3, amp=0.3)
        .layer("saw", amp=0.4)
        .layer("saw", transpose=0.3, amp=0.3)
    )
    signal.output()


SYNTH_TRACK = saws
