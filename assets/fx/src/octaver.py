"""Source-defined Sonic Pi-style octaver FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "octaver"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined octaver FX signal plan."""

    signal = sy.fx_input().octaver(super_amp=1, sub_amp=1, subsub_amp=1)
    sy.fx_output(signal, **opts)
