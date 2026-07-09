"""Source-defined Sonic Pi utility/input synth from design files: :live_audio_mono."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "live_audio_mono"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def live_audio_mono(note: object = 60, **opts: object) -> None:
    signal = sy.synth_input(note, **opts).silence(amp=0.0, release=0.01)
    signal.output()


SYNTH_TRACK = live_audio_mono
