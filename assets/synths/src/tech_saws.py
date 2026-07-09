"""Source-defined Sonic Pi synth from design files: :tech_saws."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "tech_saws"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def tech_saws(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.5, "cutoff": 105, "res": 0.35},
            **opts,
        )
        .layer("saw", transpose=-0.2, amp=0.3)
        .layer("saw", amp=0.4)
        .layer("saw", transpose=0.2, amp=0.3)
        .layer("saw", transpose=12, amp=0.15)
    )
    signal.output()


SYNTH_TRACK = tech_saws
