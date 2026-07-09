"""Source-defined Sonic Pi-style pan FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "pan"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined pan FX signal plan."""

    signal = sy.fx_input().pan(pan=0)
    sy.fx_output(signal, **opts)
