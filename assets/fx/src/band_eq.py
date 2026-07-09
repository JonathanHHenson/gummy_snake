"""Source-defined Sonic Pi-style band_eq FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "band_eq"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined band_eq FX signal plan."""

    signal = sy.fx_input().band_eq(freq=100, res=0.6, db=0.6)
    sy.fx_output(signal, **opts)
