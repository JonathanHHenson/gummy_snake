"""Source-defined Sonic Pi synth from design files: :sc808_snare."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "sc808_snare"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_snare(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.28, "cutoff": 115},
            **opts,
        )
        .layer("cnoise", amp=0.65)
        .layer("sine", transpose=7, amp=0.25)
        .layer("noise", amp=0.2)
    )
    signal.output()


SYNTH_TRACK = sc808_snare
