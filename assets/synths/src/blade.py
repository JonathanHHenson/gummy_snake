"""Source-defined Sonic Pi synth from design files: :blade."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "blade"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def blade(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.7, "cutoff": 100},
            **opts,
        )
        .layer("saw", transpose=-0.08, amp=0.45)
        .layer("saw", transpose=0.08, amp=0.45)
        .layer("sine", transpose=12, amp=0.15)
    )
    signal.output()


SYNTH_TRACK = blade
