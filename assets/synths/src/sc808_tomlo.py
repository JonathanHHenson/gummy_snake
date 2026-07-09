"""Source-defined Sonic Pi synth from design files: :sc808_tomlo."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "sc808_tomlo"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_tomlo(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.45, "cutoff": 105},
            **opts,
        )
        .layer("sine", transpose=-12, amp=0.75)
        .layer("tri", transpose=-12, amp=0.25)
    )
    signal.output()


SYNTH_TRACK = sc808_tomlo
