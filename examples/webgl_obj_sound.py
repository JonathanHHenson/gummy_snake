"""OBJ + sound demo for the first WEBGL-style software 3D milestone.

Headless/export:
    uv run python examples/webgl_obj_sound.py --backend headless --frames 1

Interactive:
    uv run python examples/webgl_obj_sound.py --backend pyglet --play-sound
"""

from __future__ import annotations

import argparse
import math
from contextlib import suppress
from pathlib import Path

import p5_py as p5
from p5_py.assets.sound import Sound
from p5_py.exceptions import BackendCapabilityError

ASSET_DIR = Path("examples/assets")
OUTPUT = Path("examples/output/webgl_obj_sound.png")
MODEL = p5.load_model(ASSET_DIR / "teapot.obj", normalize=True)
SOUND: Sound | None = None
EXPORT_CANVAS = False
PLAY_SOUND = False


def setup() -> None:
    global SOUND

    p5.create_canvas(720, 480, p5.WEBGL)
    p5.camera(0, 0, 4.2, 0, 0, 0, 0, 1, 0)
    p5.perspective(math.pi / 3, 720 / 480, 0.1, 100)
    p5.stroke(18, 20, 32)
    p5.frame_rate(60)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    SOUND = p5.load_sound(ASSET_DIR / "coin-drop-4.wav")
    if PLAY_SOUND and SOUND is not None:
        with suppress(BackendCapabilityError):
            SOUND.play()


def draw() -> None:
    orbit = p5.frame_count() * 0.35
    p5.background(10, 14, 26)
    p5.camera(math.sin(orbit) * 1.6, -0.4, 4.2, 0, 0, 0, 0, 1, 0)
    p5.ambient_light(45)
    p5.directional_light(255, 240, 220, -0.5, -0.7, -1.0)
    p5.specular_material(202, 150, 255)
    p5.shininess(8)
    p5.model(MODEL)

    if EXPORT_CANVAS and p5.frame_count() == 0:
        p5.save_canvas(str(OUTPUT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=p5.HEADLESS, choices=p5.available_backends())
    parser.add_argument("--frames", type=int, default=1)
    parser.add_argument("--play-sound", action="store_true")
    args = parser.parse_args()

    global EXPORT_CANVAS, PLAY_SOUND
    EXPORT_CANVAS = args.backend in {p5.HEADLESS, p5.PILLOW, p5.PYGLET}
    PLAY_SOUND = args.play_sound
    p5.run(setup=setup, draw=draw, backend=args.backend, max_frames=args.frames)


if __name__ == "__main__":
    main()
