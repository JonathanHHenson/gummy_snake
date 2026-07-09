"""Source-defined Sonic Pi-style nrhpf FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "nrhpf"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined nrhpf FX signal plan."""

    signal = sy.fx_input().filter(kind="high", cutoff=100, res=0.5, resonant=True, normalise=True)
    sy.fx_output(signal, **opts)
