"""Source-defined Sonic Pi-style bpf FX."""

from __future__ import annotations

from gummysnake import synth as sy

from ._common import fx_duration

NAME = "bpf"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined bpf FX signal plan."""

    signal = sy.fx_input().bandpass(centre=100, res=0.6)
    sy.fx_output(signal, **opts)
