"""Build, render, and optionally play a synth track inspired by Sonic Pi."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from gummysnake import synth as sy

OUTPUT = Path("examples/output/12_synth/tron_bikes.wav")


@sy.track(loop=True)
def tron_bikes() -> None:
    with (
        sy.synth("dsaw"),
        sy.fx("slicer", phase=sy.choose([0.25, 0.125])),
        sy.fx("reverb", room=0.5, mix=0.3),
    ):
        notes = ["b1", "b2", "e1", "e2", "b3", "e3"]
        start_note = sy.choose(sy.chord(sy.choose(notes), "minor"))
        final_note = sy.choose(sy.chord(sy.choose(notes), "minor"))

        handle = sy.play(
            start_note,
            amp=2,
            release=8,
            note_slide=4,
            cutoff=30,
            cutoff_slide=4,
            detune=sy.rrand(0, 0.2),
        )
        sy.control(handle, note=final_note, cutoff=sy.rrand(80, 120))
    sy.sleep(8)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=16.0, help="seconds to render")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--no-play", action="store_true", help="skip platform audio playback")
    parser.add_argument("--no-save", action="store_true", help="skip writing the WAV file")
    args = parser.parse_args()

    track = tron_bikes()
    render_duration = sy.duration(secs=args.duration)
    print(track.explain())
    if not args.no_save:
        saved = track.save(args.output, duration=render_duration)
        print(f"saved {saved}")
    if not args.no_play:
        print("playing tron_bikes...")
        playback = track.play(duration=render_duration)
        if isinstance(playback, sy.TrackPlayback):
            playback.wait_until_stop()
            if playback.error is not None:
                print(f"playback unavailable: {playback.error}")

    sound: gs.Sound = track.to_sound("tron_bikes.wav", duration=render_duration)
    print(f"rendered in-memory sound: duration={sound.duration:.2f}s bytes={len(sound.to_bytes())}")


if __name__ == "__main__":
    main()
