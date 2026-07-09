"""Source-defined Sonic Pi-style panslicer FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "panslicer"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined panslicer FX signal plan."""

    signal = sy.fx_input().panslicer(
        phase=0.25,
        pan_min=-1,
        pan_max=1,
        pulse_width=0.5,
        smooth=0,
        smooth_up=0,
        smooth_down=0,
        probability=0,
        prob_pos=0,
        phase_offset=0,
        wave=1,
        invert_wave=0,
    )
    sy.fx_output(signal, **opts)
