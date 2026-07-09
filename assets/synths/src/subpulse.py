"""Source-defined Sonic Pi synth from design files: :subpulse."""

from __future__ import annotations

from gummysnake import synth as sy
from _common import synth_duration

SYNTH_NAME = "subpulse"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def subpulse(note: object = 60, **opts: object) -> None:
    sub_amp = opts.pop("sub_amp", 1)
    sub_detune = opts.pop("sub_detune", -12)
    signal = (
        sy.synth_input(
            note,
            defaults={
                "release": 1,
                "env_curve": 1,
                "cutoff": 100,
                "pulse_width": 0.5,
                "amp_fudge": 0.8,
                "normalise": True,
            },
            **opts,
        )
        .layer("pulse")
        .layer("sine", transpose=sub_detune, amp=sub_amp)
    )
    signal.output()


SYNTH_TRACK = subpulse
