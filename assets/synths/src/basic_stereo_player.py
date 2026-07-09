"""Source-defined Sonic Pi synth from design files: :basic_stereo_player."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "basic_stereo_player"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def basic_stereo_player(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(note, **opts).sample("loop_amen", amp=0.4, finish=0.08)
    signal.output()


SYNTH_TRACK = basic_stereo_player
