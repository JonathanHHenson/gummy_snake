"""Source-defined Sonic Pi-style reverb FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "reverb"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined reverb FX signal plan."""

    signal = sy.fx_input().reverb(room=0.6, damp=0.5)
    output_opts: dict[str, object] = {"mix": 0.4}
    output_opts.update(opts)
    sy.fx_output(signal, **output_opts)
