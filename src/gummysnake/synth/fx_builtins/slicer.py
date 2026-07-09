"""Source-defined Sonic Pi-style slicer FX."""

from __future__ import annotations

from gummysnake import synth as sy

from ._common import fx_duration

NAME = "slicer"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined slicer FX signal plan."""

    signal = sy.fx_input().slicer(
        phase=0.25,
        amp_min=0,
        amp_max=1,
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
