"""Control a running FX handle while using scales, rings, and chords."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gummysnake import BackendCapabilityError
from gummysnake import synth as sy

OUTPUT = Path("examples/output/12_synth/control_fx_and_scales.wav")


@sy.track(loop_times=4, seed=77)
def control_fx() -> None:
    notes = sy.scale("e3", "minor_pentatonic", num_octaves=2)
    rhythm = sy.ring(0.25, 0.25, 0.5, 0.125, 0.125)
    with sy.synth("tb303"), sy.fx("reverb", room=0.4, mix=0.2) as reverb:
        sy.play(sy.chord("e2", "minor"), release=1.5, amp=0.25)
        with sy.loop(times=8):
            step = sy.tick()
            sy.play(notes.look(), release=0.12, cutoff=sy.rrand(70, 120), amp=0.4)
            sy.control(reverb, mix=0.2 + (step % 4) * 0.1)
            sy.sleep(rhythm.tick("rhythm"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=8.0, help="seconds to render")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--mp3", type=Path, help="also export MP3 when ffmpeg is available")
    parser.add_argument("--no-play", action="store_true", help="skip platform audio playback")
    parser.add_argument("--no-save", action="store_true", help="skip writing the WAV file")
    args = parser.parse_args()

    track = control_fx()
    render_duration = sy.duration(secs=args.duration)
    if not args.no_save:
        saved = track.save(args.output, duration=render_duration)
        print(f"saved {saved}")
    if args.mp3 is not None:
        try:
            saved_mp3 = track.save(args.mp3, format=sy.Format.MP3, duration=render_duration)
            print(f"saved {saved_mp3}")
        except BackendCapabilityError as exc:
            print(exc)
    print(track.explain())
    if not args.no_play:
        print("playing control_fx...")
        playback = track.play(duration=render_duration)
        if isinstance(playback, sy.TrackPlayback):
            playback.wait_until_stop()
            if playback.error is not None:
                print(f"playback unavailable: {playback.error}")


if __name__ == "__main__":
    main()
