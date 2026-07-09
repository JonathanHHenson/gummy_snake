"""Source-defined Sonic Pi synth from design files: :sc808_rimshot."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "sc808_rimshot"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_rimshot(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.12, "cutoff": 120},
            **opts,
        )
        .layer("sine", transpose=12, amp=0.35)
        .layer("cnoise", amp=0.55)
    )
    signal.output()


SYNTH_TRACK = sc808_rimshot
