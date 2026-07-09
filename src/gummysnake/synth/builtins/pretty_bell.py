"""Source-defined Sonic Pi synth from design files: :pretty_bell."""

from __future__ import annotations

from gummysnake import synth as sy
from gummysnake.synth.builtins._common import synth_duration

SYNTH_NAME = "pretty_bell"
DURATION = synth_duration(SYNTH_NAME)


@sy.synth(name=SYNTH_NAME)
def pretty_bell(note: object = 60, **opts: object) -> None:
    signal = (
        sy.synth_input(
            note,
            defaults={"release": 1.2},
            **opts,
        )
        .layer("sine", amp=0.65)
        .layer("sine", transpose=12, amp=0.35)
        .layer("sine", transpose=19.02, amp=0.22)
        .layer("sine", transpose=24.4, amp=0.12)
    )
    signal.output()


SYNTH_TRACK = pretty_bell
