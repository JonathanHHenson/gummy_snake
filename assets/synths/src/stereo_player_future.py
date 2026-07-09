"""Source-defined Sonic Pi synth from design files: :stereo_player-future."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.srcmon import synth_duration

SYNTH_NAME = "stereo_player-future"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def stereo_player_future(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(note, **opts).sample("loop_amen", amp=0.4, finish=0.08)
    signal.output()


SYNTH_TRACK = stereo_player_future
