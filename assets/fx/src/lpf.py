"""Source-defined Sonic Pi-style lpf FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "lpf"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined lpf FX signal plan."""

    signal = sy.fx_input().filter(kind="low", cutoff=100)
    sy.fx_output(signal, **opts)
