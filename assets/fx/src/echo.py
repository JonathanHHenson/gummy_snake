"""Source-defined Sonic Pi-style echo FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "echo"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined echo FX signal plan."""

    signal = sy.fx_input().echo(phase=0.25, decay=2, max_phase=2)
    sy.fx_output(signal, **opts)
