"""Source-defined Sonic Pi synth from design files: :sc808_cowbell."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "sc808_cowbell"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_cowbell(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 125},
            **opts,
        )
        .layer("square", transpose=7, amp=0.55)
        .layer("square", transpose=12, amp=0.45)
        .layer("cnoise", amp=0.08)
    )
    signal.output()


SYNTH_TRACK = sc808_cowbell
