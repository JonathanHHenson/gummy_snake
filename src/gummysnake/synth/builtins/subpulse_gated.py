"""Source-defined Sonic Pi synth from design files: :subpulse_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "subpulse_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def subpulse_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 100, "pulse_width": 0.5, "sustain": 0.25},
            **opts,
        )
        .layer("pulse", amp=0.65)
        .layer("sine", transpose=-12, amp=0.55)
    )
    signal.output()


SYNTH_TRACK = subpulse_gated
