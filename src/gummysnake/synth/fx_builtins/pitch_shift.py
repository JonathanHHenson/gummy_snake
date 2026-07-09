"""Source-defined Sonic Pi-style pitch_shift FX."""

from __future__ import annotations

from gummysnake import synth as sy

from ._common import fx_duration

NAME = "pitch_shift"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined pitch_shift FX signal plan."""

    signal = sy.fx_input().pitch_shift(pitch=0, window_size=0.2, pitch_dis=0.0, time_dis=0.0)
    sy.fx_output(signal, **opts)
