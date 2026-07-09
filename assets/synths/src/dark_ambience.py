"""Source-defined Sonic Pi synth from design files: :dark_ambience."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "dark_ambience"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dark_ambience(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 1.0, "cutoff": 100},
            **opts,
        )
        .layer("sine", amp=0.35)
        .layer("tri", transpose=12, amp=0.25)
        .layer("saw", transpose=24, amp=0.15)
        .layer("pnoise", amp=0.12)
    )
    signal.output()


SYNTH_TRACK = dark_ambience
