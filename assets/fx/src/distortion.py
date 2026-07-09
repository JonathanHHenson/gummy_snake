"""Source-defined Sonic Pi-style distortion FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "distortion"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined distortion FX signal plan."""

    signal = sy.fx_input().distortion_shape(distort=0.5)
    sy.fx_output(signal, **opts)
