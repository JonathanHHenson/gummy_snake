"""Source-defined Sonic Pi synth from design files: :sc808_congahi."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "sc808_congahi"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def sc808_congahi(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 0.3, "cutoff": 110},
            **opts,
        )
        .layer("sine", transpose=5, amp=0.65)
        .layer("tri", transpose=17, amp=0.22)
        .layer("cnoise", amp=0.06)
    )
    signal.output()


SYNTH_TRACK = sc808_congahi
