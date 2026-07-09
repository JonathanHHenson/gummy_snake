"""Acid bass, lunar ambience, and delayed FM drums as a synth track."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gummysnake import synth as sy

OUTPUT = Path("examples/output/12_synth/acid_walk.wav")

E_MINOR = sy.chord("e3", "minor")
A_MINOR_SEVEN = sy.chord("a3", "m7")
E_OCTAVES = sy.ring("e2", "e3", "e4")


@sy.track(seed=303)
def acid_walk() -> None:
    """Port of the Sonic Pi acid walk into Gummy Snake's bounded synth API."""

    with sy.thread(name="delayed_fm_drums"), sy.synth("fm"):
        sy.sleep(2)
        with sy.loop():
            with sy.loop(times=28):
                sy.sample("drum_bass_hard", amp=0.8)
                sy.sleep(0.25)
                sy.play("e2", release=0.2)
                sy.sample("elec_cymbal", rate=12, amp=0.6)
                sy.sleep(0.25)
            sy.sleep(4)

    with sy.synth("tb303"), sy.fx("reverb") as reverb, sy.loop():
        sy.control(reverb, mix=sy.rrand(0, 0.3))
        with sy.fx("slicer", phase=0.125):
            sy.sample("ambi_lunar_land", sustain=0, release=8, amp=2)

        sy.control(reverb, mix=sy.rrand(0, 0.6))
        tb303_release = sy.rrand(0.05, 0.3)
        with sy.loop(times=64):
            sy.play(
                sy.choose(E_MINOR),
                release=tb303_release,
                cutoff=sy.rrand(50, 90),
                amp=0.5,
            )
            sy.sleep(0.125)

        sy.control(reverb, mix=sy.rrand(0, 0.6))
        prophet_release = sy.rrand(0.1, 0.2)
        with sy.synth("prophet"), sy.loop(times=32):
            sy.sleep(0.125)
            sy.play(
                sy.choose(A_MINOR_SEVEN),
                release=prophet_release,
                cutoff=sy.rrand(40, 130),
                amp=0.7,
            )

        sy.control(reverb, mix=sy.rrand(0, 0.6))
        bright_release = sy.rrand(0.05, 0.3)
        with sy.loop(times=32):
            sy.play(
                sy.choose(E_MINOR),
                release=bright_release,
                cutoff=sy.rrand(110, 130),
                amp=0.4,
            )
            sy.sleep(0.125)

        sy.control(reverb, mix=sy.rrand(0, 0.6))
        with sy.fx("echo", phase=0.25, decay=8), sy.loop(times=16):
            sy.play(
                sy.choose(sy.chord(sy.choose(E_OCTAVES), "m7")),
                release=0.05,
                cutoff=sy.rrand(50, 129),
                amp=0.5,
            )
            sy.sleep(0.125)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=24.0, help="seconds to render")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--no-play", action="store_true", help="skip platform audio playback")
    parser.add_argument("--no-save", action="store_true", help="skip writing the WAV file")
    args = parser.parse_args()

    track = acid_walk()
    render_duration = sy.duration(secs=args.duration)
    if not args.no_save:
        saved = track.save(args.output, duration=render_duration)
        print(f"saved {saved}")
    print(track.physical_plan(duration=render_duration).explain())
    if not args.no_play:
        print("playing acid_walk...")
        playback = track.play(duration=render_duration)
        if isinstance(playback, sy.TrackPlayback):
            playback.wait_until_stop()
            if playback.error is not None:
                print(f"playback unavailable: {playback.error}")


if __name__ == "__main__":
    main()
