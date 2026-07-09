"""Source-defined Sonic Pi-style ring_mod FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "ring_mod"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined ring_mod FX signal plan."""

    signal = sy.fx_input().ring_mod(freq=30, mod_amp=1)
    sy.fx_output(signal, **opts)
