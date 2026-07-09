"""Source-defined Sonic Pi-style vowel FX."""

from __future__ import annotations

from gummysnake import synth as sy

from _common import fx_duration

NAME = "vowel"
DURATION = fx_duration(NAME)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    """Record the source-defined vowel FX signal plan."""

    signal = sy.fx_input().vowel(voice=0, vowel_sound=1)
    sy.fx_output(signal, **opts)
