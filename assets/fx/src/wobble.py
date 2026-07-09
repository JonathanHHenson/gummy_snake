"""Source-defined Sonic Pi-style wobble FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "wobble"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined wobble FX signal plan."""

    signal = sy.fx_input().wobble(
        phase=0.5,
        cutoff_min=60,
        cutoff_max=120,
        res=0.8,
        pulse_width=0.5,
        filter=0,
        smooth=0,
        smooth_up=0,
        smooth_down=0,
        phase_offset=0,
        wave=0,
        invert_wave=0,
        probability=0,
        prob_pos=0,
    )
    sy.fx_output(signal, **opts)
