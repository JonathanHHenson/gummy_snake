"""Source-defined Sonic Pi synth from design files: :dpulse."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "dpulse"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def dpulse(note: object = 60, **opts: object) -> None:
    detune = opts.pop("detune", 0.1)
    dpulse_width = opts.pop("dpulse_width", -1)
    if isinstance(dpulse_width, int | float) and dpulse_width == -1:
        dpulse_width = opts.get("pulse_width", 0.5)
    signal = (
        sy.synth_input(
            note,
            defaults={
                "release": 1,
                "env_curve": 1,
                "cutoff": 100,
                "pulse_width": 0.5,
                "amp_fudge": 1.1,
                "normalise": True,
            },
            **opts,
        )
        .layer("pulse", amp=0.5)
        .layer("pulse", transpose=detune, amp=0.5, pulse_width=dpulse_width)
    )
    signal.output()


SYNTH_TRACK = dpulse
