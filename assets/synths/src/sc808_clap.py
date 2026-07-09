"""Source-defined Sonic Pi synth from design files: :sc808_clap."""

from __future__ import annotations

from _common import synth_duration

from gummysnake import synth as sy

SYNTH_NAME = "sc808_clap"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_clap(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.22, "cutoff": 120},
            **opts,
        )
        .layer("cnoise", amp=0.8)
        .layer("noise", amp=0.25)
    )
    signal.output()


SYNTH_TRACK = sc808_clap
