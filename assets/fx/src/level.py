"""Source-defined Sonic Pi-style level FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "level"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined level FX signal plan."""

    signal = sy.fx_input().level()
    sy.fx_output(signal, **opts)
