"""Source-defined Sonic Pi synth from design files: :chipbass_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "chipbass_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def chipbass_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.3, "cutoff": 95, "sustain": 0.25},
            **opts,
        )
        .layer("square", transpose=-12, amp=0.55)
        .layer("tri", transpose=-24, amp=0.35)
    )
    signal.output()


SYNTH_TRACK = chipbass_gated
