"""Source-defined Sonic Pi synth from design files: :chipbass."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "chipbass"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def chipbass(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.3, "cutoff": 95},
            **opts,
        )
        .layer("square", transpose=-12, amp=0.55)
        .layer("tri", transpose=-24, amp=0.35)
    )
    signal.output()


SYNTH_TRACK = chipbass
