"""Source-defined Sonic Pi synth from design files: :mod_saw."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.src._common import synth_duration

SYNTH_NAME = "mod_saw"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def mod_saw(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 100},
            **opts,
        )
        .layer("saw", amp=0.55)
        .layer("saw", transpose=7, amp=0.35)
    )
    signal.output()


SYNTH_TRACK = mod_saw
