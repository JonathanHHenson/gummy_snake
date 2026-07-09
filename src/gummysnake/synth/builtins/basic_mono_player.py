"""Source-defined Sonic Pi synth from design files: :basic_mono_player."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "basic_mono_player"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def basic_mono_player(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(note, **opts).sample("loop_amen", amp=0.4, finish=0.08)
    signal.output()


SYNTH_TRACK = basic_mono_player
