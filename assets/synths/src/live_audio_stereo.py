"""Source-defined Sonic Pi utility/input synth from design files: :live_audio_stereo."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "live_audio_stereo"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def live_audio_stereo(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(note, **opts).silence(amp=0.0, release=0.01)
    signal.output()


SYNTH_TRACK = live_audio_stereo
