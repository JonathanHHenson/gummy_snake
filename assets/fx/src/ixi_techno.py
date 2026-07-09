"""Source-defined Sonic Pi-style ixi_techno FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "ixi_techno"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined ixi_techno FX signal plan."""

    signal = sy.fx_input().ixi_techno(
        phase=4, phase_offset=0, cutoff_min=60, cutoff_max=120, res=0.8
    )
    sy.fx_output(signal, **opts)
