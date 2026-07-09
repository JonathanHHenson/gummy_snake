"""Source-defined Sonic Pi synth from design files: :stereo_warp_sample."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "stereo_warp_sample"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def stereo_warp_sample(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(note, **opts).sample("loop_amen", amp=0.4, finish=0.08)
    signal.output()


SYNTH_TRACK = stereo_warp_sample
