"""Source-defined Sonic Pi synth from design files: :hoover."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "hoover"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def hoover(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 1.0, "cutoff": 130},
            **opts,
        )
        .layer("saw", transpose=-12, amp=0.35)
        .layer("saw", transpose=-0.12, amp=0.35)
        .layer("saw", transpose=0.12, amp=0.35)
        .layer("pulse", transpose=0.31, amp=0.25)
    )
    signal.output()


SYNTH_TRACK = hoover
