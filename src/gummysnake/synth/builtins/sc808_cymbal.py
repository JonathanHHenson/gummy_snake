"""Source-defined Sonic Pi synth from design files: :sc808_cymbal."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "sc808_cymbal"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_cymbal(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.8, "cutoff": 127},
            **opts,
        )
        .layer("cnoise", amp=0.6)
        .layer("gnoise", amp=0.4)
        .layer("square", transpose=24, amp=0.12)
    )
    signal.output()


SYNTH_TRACK = sc808_cymbal
