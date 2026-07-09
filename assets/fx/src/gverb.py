"""Source-defined Sonic Pi-style gverb FX."""

from __future__ import annotations

from _common import fx_duration

from gummysnake import synth as sy

NAME = "gverb"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined gverb FX signal plan."""

    signal = sy.fx_input().gverb(
        room=10, release=3, spread=0.5, damp=0.5, pre_damp=0.5, dry=1, ref_level=0.7, tail_level=0.5
    )
    output_opts: dict[str, object] = {"mix": 0.4}
    output_opts.update(opts)
    sy.fx_output(signal, **output_opts)
