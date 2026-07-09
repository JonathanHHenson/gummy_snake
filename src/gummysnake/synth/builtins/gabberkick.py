"""Source-defined Sonic Pi synth from design files: :gabberkick."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "gabberkick"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def gabberkick(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.45, "cutoff": 95, "res": 0.4},
            **opts,
        )
        .layer("sine", transpose=-26, amp=0.95)
        .layer("sine", transpose=-14, amp=0.35)
        .layer("cnoise", amp=0.08)
    )
    signal.output()


SYNTH_TRACK = gabberkick
