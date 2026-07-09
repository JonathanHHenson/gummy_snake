"""Source-defined Sonic Pi-style compressor FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "compressor"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined compressor FX signal plan."""

    signal = sy.fx_input().compressor(
        threshold=0.2, clamp_time=0.01, slope_above=0.5, slope_below=1, relax_time=0.01
    )
    sy.fx_output(signal, **opts)
