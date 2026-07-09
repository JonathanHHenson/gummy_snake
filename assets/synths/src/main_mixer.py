"""Source-defined Sonic Pi utility/input synth from design files: :main_mixer."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.src._common import synth_duration

SYNTH_NAME = "main_mixer"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def main_mixer(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(note, **opts).silence(amp=0.0, release=0.01)
    signal.output()


SYNTH_TRACK = main_mixer
