"""Source-defined Sonic Pi synth from design files: :mod_dsaw_gated."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "mod_dsaw_gated"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def mod_dsaw_gated(note: object = 60, **opts: object) -> None:
    detune = opts.pop("detune", 0.1)
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.35, "cutoff": 100, "sustain": 0.25},
            **opts,
        )
        .layer("saw", amp=0.45)
        .layer("saw", transpose=detune, amp=0.35)
        .layer("saw", transpose=7, amp=0.25)
    )
    signal.output()


SYNTH_TRACK = mod_dsaw_gated
