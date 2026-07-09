"""Source-defined Sonic Pi-style whammy FX."""

from __future__ import annotations

from gummysnake import synth as sy

from ._common import fx_duration

NAME = "whammy"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined whammy FX signal plan."""

    signal = sy.fx_input().whammy(transpose=12, deltime=0.05, max_delay_time=1, grainsize=0.075)
    sy.fx_output(signal, **opts)
