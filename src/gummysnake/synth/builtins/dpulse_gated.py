"""Source-defined Sonic Pi synth from design files: :dpulse_gated."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "dpulse_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dpulse_gated(note: object = 60, **opts: object) -> None:
    detune = opts.pop("detune", 0.1)
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 100, "pulse_width": 0.45, "sustain": 0.25},
            **opts,
        )
        .layer("pulse", amp=0.55)
        .layer("pulse", transpose=detune, amp=0.55)
    )
    signal.output()


SYNTH_TRACK = dpulse_gated
