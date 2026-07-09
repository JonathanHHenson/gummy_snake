"""Source-defined Sonic Pi-style krush FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "krush"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined krush FX signal plan."""

    signal = sy.fx_input().krush_shape(gain=5).filter(kind="low", cutoff=100, res=0, resonant=True)
    sy.fx_output(signal, **opts)
