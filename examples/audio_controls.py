"""Sound loading and control demo.

Headless/export:
    uv run python examples/audio_controls.py --headless --frames 1

Interactive playback attempt:
    uv run python examples/audio_controls.py --interactive --play
"""

from __future__ import annotations

import argparse
from contextlib import suppress
from pathlib import Path

import p5
from p5.assets.sound import Sound
from p5.exceptions import BackendCapabilityError

ASSET_DIR = Path("examples/assets")
OUTPUT = Path("examples/output/audio_controls.png")
SOUND: Sound | None = None
EXPORT_CANVAS = False
TRY_PLAY = False
STATUS = "Loaded sound controls demo."


def setup() -> None:
    global SOUND, STATUS

    p5.create_canvas(720, 360)
    p5.frame_rate(12)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    SOUND = p5.create_audio(ASSET_DIR / "coin-drop-4.wav")
    SOUND.volume(0.65)
    SOUND.rate(1.1)
    SOUND.pan(-0.35)

    if TRY_PLAY:
        try:
            SOUND.play()
            STATUS = "Playback started."
        except BackendCapabilityError as exc:
            STATUS = str(exc)


def draw_meter(
    label: str, value: float, *, left: float, top: float, width: float, accent: tuple[int, int, int]
) -> None:
    p5.fill(34, 40, 58)
    p5.no_stroke()
    p5.rect(left, top, width, 24)
    p5.fill(*accent)
    p5.rect(left, top, max(0.0, min(width, value * width)), 24)
    p5.fill(240)
    p5.text(f"{label}: {value:.2f}", left, top - 10)


def draw() -> None:
    p5.background(12, 16, 28)

    if SOUND is None:
        p5.fill(255)
        p5.text("Could not load examples/assets/coin-drop-4.wav", 32, 64)
        return

    volume = SOUND.volume()
    rate = SOUND.rate()
    pan = SOUND.pan()
    duration = SOUND.duration

    p5.fill(244)
    p5.text_size(20)
    p5.text("create_audio() / Sound controls", 32, 42)
    p5.text_size(13)
    p5.text(f"Asset: {SOUND.path}", 32, 72)
    p5.text(
        f"Duration: {duration:.2f}s" if duration is not None else "Duration: unavailable", 32, 94
    )
    p5.text(STATUS, 32, 116)
    p5.text("Use --play to attempt native playback on supported systems.", 32, 138)

    draw_meter("volume", volume, left=32, top=176, width=280, accent=(109, 213, 158))
    draw_meter("rate", min(rate / 2.0, 1.0), left=32, top=236, width=280, accent=(112, 178, 255))

    p5.fill(230)
    p5.text(f"pan: {pan:.2f}", 32, 314)
    center_x = 500
    center_y = 220
    p5.stroke(84, 96, 132)
    p5.line(center_x - 120, center_y, center_x + 120, center_y)
    p5.no_stroke()
    p5.fill(245, 132, 111)
    p5.circle(center_x + pan * 100.0, center_y, 34)
    p5.fill(210)
    p5.text("L", center_x - 128, center_y + 5)
    p5.text("R", center_x + 124, center_y + 5)

    pulse = 18 + (rate * 10)
    p5.fill(130, 114, 255, 110)
    p5.circle(560, 110, pulse * (1 + (p5.frame_count() % 6) * 0.2))

    if EXPORT_CANVAS and p5.frame_count() == 0:
        p5.save_canvas(str(OUTPUT))


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=1)
    parser.add_argument("--play", action="store_true", help="Attempt native audio playback.")
    args = parser.parse_args()

    global EXPORT_CANVAS, TRY_PLAY
    EXPORT_CANVAS = args.headless is not False or args.frames is not None
    TRY_PLAY = args.play
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)

    if SOUND is not None:
        with suppress(BackendCapabilityError):
            SOUND.stop()


if __name__ == "__main__":
    main()
