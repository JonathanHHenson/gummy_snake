"""Source-defined Sonic Pi-style tanh FX."""

from __future__ import annotations

from gummysnake import synth as sy

from ._common import fx_duration

NAME = "tanh"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined tanh FX signal plan."""

    signal = sy.fx_input().tanh_shape(krunch=5)
    sy.fx_output(signal, **opts)
