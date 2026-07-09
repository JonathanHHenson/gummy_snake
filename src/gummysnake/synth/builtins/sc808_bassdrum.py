"""Source-defined Sonic Pi synth from design files: :sc808_bassdrum."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "sc808_bassdrum"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_bassdrum(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.45, "cutoff": 90},
            **opts,
        )
        .layer("sine", transpose=-24, amp=0.9)
        .layer("sine", transpose=-12, amp=0.3)
        .layer("cnoise", amp=0.05)
    )
    signal.output()


SYNTH_TRACK = sc808_bassdrum
