"""Source-defined Sonic Pi-style bitcrusher FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "bitcrusher"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined bitcrusher FX signal plan."""

    signal = sy.fx_input().decimator(sample_rate=10000, bits=8, cutoff=0)
    sy.fx_output(signal, **opts)
