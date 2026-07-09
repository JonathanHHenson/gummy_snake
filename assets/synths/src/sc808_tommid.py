"""Source-defined Sonic Pi synth from design files: :sc808_tommid."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "sc808_tommid"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_tommid(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.38, "cutoff": 105},
            **opts,
        )
        .layer("sine", transpose=-5, amp=0.75)
        .layer("tri", transpose=-5, amp=0.25)
    )
    signal.output()


SYNTH_TRACK = sc808_tommid
