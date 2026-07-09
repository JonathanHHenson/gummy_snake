"""Source-defined Sonic Pi utility/input synth from design files: :sound_in_stereo."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "sound_in_stereo"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sound_in_stereo(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(note, **opts).silence(amp=0.0, release=0.01)
    signal.output()


SYNTH_TRACK = sound_in_stereo
