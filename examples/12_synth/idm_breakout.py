"""IDM-style breakbeat composition with synth loops and nested track calls."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gummysnake import synth as sy

OUTPUT = Path("examples/output/12_synth/idm_breakout.wav")


@sy.track(seed=500)
def play_bb(n: int) -> None:
    sy.sample("drum_heavy_kick")
    sy.sample(
        "ambi_drone",
        rate=sy.choose([0.25, 0.5, 0.125, 1]),
        amp=0.25,
    ).when(sy.rand() < 0.125)
    sy.sample(
        "ambi_lunar_land",
        rate=sy.choose([0.5, 0.125, 1, -1, -0.5]),
        amp=0.25,
    ).when(sy.rand() < 0.125)
    sy.sample(
        "loop_amen",
        attack=0,
        release=0.05,
        start=1 - (1.0 / n),
        rate=sy.choose([1] * 6 + [-1]),
    )
    sy.sleep(sy.sample_duration("loop_amen") / n)


@sy.track(loop=True, seed=900)
def idm_breakout() -> None:
    sy.play_bb(sy.choose([1, 2, 4, 8, 16]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=12.0, help="seconds to render")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--no-play", action="store_true", help="skip platform audio playback")
    parser.add_argument("--no-save", action="store_true", help="skip writing the WAV file")
    args = parser.parse_args()

    track = idm_breakout()
    render_duration = sy.duration(secs=args.duration)
    if not args.no_save:
        saved = track.save(args.output, duration=render_duration)
        print(f"saved {saved}")
    print(track.physical_plan(duration=render_duration).explain())
    if not args.no_play:
        print("playing idm_breakout...")
        playback = track.play(duration=render_duration)
        if isinstance(playback, sy.TrackPlayback):
            playback.wait_until_stop()
            if playback.error is not None:
                print(f"playback unavailable: {playback.error}")


if __name__ == "__main__":
    main()
