"""Load a sound asset and control its metadata without requiring playback."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

ASSETS = Path("examples/assets")
OUTPUT = Path("examples/output/03_assets/sound_asset_metadata.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
SOUND: gs.Sound | None = None


def preload() -> None:
    global SOUND
    SOUND = gs.load_sound(ASSETS / "coin-drop-4.wav")
    SOUND.volume(0.6)
    SOUND.rate(1.1)
    SOUND.pan(-0.25)


def setup() -> None:
    assert SOUND is not None
    gs.create_canvas(560, 260)
    SOUND.play()


def draw() -> None:
    assert SOUND is not None
    gs.background(32, 36, 48)
    gs.fill(245)
    gs.text_size(18)
    gs.text("Sound asset", 32, 42)
    gs.text_size(15)
    gs.text(f"path: {SOUND.path}", 32, 86)
    gs.text(f"duration: {SOUND.duration:.3f}s", 32, 118)
    gs.text(
        f"volume: {SOUND.volume():.2f}  rate: {SOUND.rate():.2f}  pan: {SOUND.pan():.2f}",
        32,
        150,
    )
    gs.text("Playback is available when a platform audio player exists.", 32, 204)

    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(preload=preload, setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
