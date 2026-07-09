"""Source-defined Sonic Pi synth from design files: :pnoise."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "pnoise"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def pnoise(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(
        note,
        defaults={"release": 0.35, "cutoff": 110},
        **opts,
    ).layer("pnoise")
    signal.output()


SYNTH_TRACK = pnoise
