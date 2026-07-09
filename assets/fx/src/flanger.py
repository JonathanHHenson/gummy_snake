"""Source-defined Sonic Pi-style flanger FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "flanger"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined flanger FX signal plan."""

    signal = sy.fx_input().flanger(
        phase=4,
        phase_offset=0,
        wave=4,
        invert_wave=0,
        stereo_invert_wave=0,
        pulse_width=0.5,
        delay=5,
        max_delay=20,
        depth=5,
        feedback=0,
        decay=2,
        invert_flange=0,
    )
    sy.fx_output(signal, **opts)
