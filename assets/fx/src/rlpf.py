"""Source-defined Sonic Pi-style rlpf FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "rlpf"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined rlpf FX signal plan."""

    signal = sy.fx_input().filter(kind="low", cutoff=100, res=0.5, resonant=True)
    sy.fx_output(signal, **opts)
