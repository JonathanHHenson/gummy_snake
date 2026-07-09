"""Source-defined Sonic Pi synth from design files: :sc808_claves."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "sc808_claves"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_claves(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.1, "cutoff": 120},
            **opts,
        )
        .layer("sine", transpose=19, amp=0.55)
        .layer("cnoise", amp=0.18)
    )
    signal.output()


SYNTH_TRACK = sc808_claves
