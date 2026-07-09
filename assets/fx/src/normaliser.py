"""Source-defined Sonic Pi-style normaliser FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "normaliser"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined normaliser FX signal plan."""

    signal = sy.fx_input().normalise(level=1)
    sy.fx_output(signal, **opts)
