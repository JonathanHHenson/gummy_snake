"""Source-defined Sonic Pi synth from design files: :sc808_tomhi."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "sc808_tomhi"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_tomhi(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.32, "cutoff": 105},
            **opts,
        )
        .layer("sine", amp=0.75)
        .layer("tri", amp=0.25)
    )
    signal.output()


SYNTH_TRACK = sc808_tomhi
