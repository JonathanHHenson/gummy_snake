"""Source-defined Sonic Pi synth from design files: :dtri."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "dtri"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dtri(note: object = 60, **opts: object) -> None:
    detune = opts.pop("detune", 0.1)
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 100},
            **opts,
        )
        .layer("tri", amp=0.55)
        .layer("tri", transpose=detune, amp=0.55)
    )
    signal.output()


SYNTH_TRACK = dtri
