"""Source-defined Sonic Pi synth from design files: :organ_tonewheel."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "organ_tonewheel"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def organ_tonewheel(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.8},
            **opts,
        )
        .layer("sine", transpose=-12, amp=0.25)
        .layer("sine", amp=0.55)
        .layer("sine", transpose=7, amp=0.18)
        .layer("sine", transpose=12, amp=0.15)
        .layer("sine", transpose=19, amp=0.08)
    )
    signal.output()


SYNTH_TRACK = organ_tonewheel
