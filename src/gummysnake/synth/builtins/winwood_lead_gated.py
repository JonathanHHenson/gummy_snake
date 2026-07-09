"""Source-defined Sonic Pi synth from design files: :winwood_lead_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "winwood_lead_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def winwood_lead_gated(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 110, "pulse_width": 0.4, "sustain": 0.25},
            **opts,
        )
        .layer("pulse", amp=0.55)
        .layer("saw", transpose=12, amp=0.25)
        .layer("sine", transpose=19, amp=0.1)
    )
    signal.output()


SYNTH_TRACK = winwood_lead_gated
