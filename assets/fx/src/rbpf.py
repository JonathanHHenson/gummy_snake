"""Source-defined Sonic Pi-style rbpf FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "rbpf"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined rbpf FX signal plan."""

    signal = sy.fx_input().bandpass(centre=100, res=0.6, resonant=True)
    sy.fx_output(signal, **opts)
