"""Wobble rhythm and ambient choir loops as a standalone synth track."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gummysnake import synth as sy

OUTPUT = Path("examples/output/12_synth/wob_rythm.wav")


@sy.track(seed=200)
def wob_rythm() -> None:
    with sy.fx("reverb"), sy.thread(), sy.loop():
        rate = sy.choose([0.5, 1 / 3, 3 / 5])
        with sy.loop(times=8):
            sy.sample("ambi_choir", rate=rate, pan=sy.rrand(-1, 1), amp=0.35)
            sy.sleep(0.5)

    with sy.fx("wobble", phase=2), sy.fx("echo", mix=0.6), sy.loop():
        sy.sample("drum_heavy_kick")
        sy.sample("bass_hit_c", rate=0.8, amp=0.4)
        sy.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=12.0, help="seconds to render")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--no-play", action="store_true", help="skip platform audio playback")
    parser.add_argument("--no-save", action="store_true", help="skip writing the WAV file")
    args = parser.parse_args()

    track = wob_rythm()
    render_duration = sy.duration(secs=args.duration)
    if not args.no_save:
        saved = track.save(args.output, duration=render_duration)
        print(f"saved {saved}")
    print(track.physical_plan(duration=render_duration).explain())
    if not args.no_play:
        print("playing wob_rythm...")
        playback = track.play(duration=render_duration)
        if isinstance(playback, sy.TrackPlayback):
            playback.wait_until_stop()
            if playback.error is not None:
                print(f"playback unavailable: {playback.error}")


if __name__ == "__main__":
    main()
