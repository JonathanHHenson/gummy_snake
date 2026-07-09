"""Source-defined Sonic Pi synth from design files: :mod_fm."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "mod_fm"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def mod_fm(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "divisor": 2, "depth": 1.2, "cutoff": 100},
            **opts,
        )
        .layer("fm", amp=0.55)
        .layer("fm", transpose=7, amp=0.35)
    )
    signal.output()


SYNTH_TRACK = mod_fm
