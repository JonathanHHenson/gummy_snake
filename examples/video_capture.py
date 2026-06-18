"""Camera capture demo for the staged native media API.

Interactive:
    uv run python examples/video_capture.py

Notes:
    - Requires the optional media extra: `uv add --optional media opencv-python-headless`
    - Uses the first available camera by default
    - Some platforms may prompt for camera permission on first run
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5
from p5.assets.media import Capture
from p5.exceptions import BackendCapabilityError

OUTPUT = Path("examples/output/video_capture.png")
CAMERA: Capture | None = None
EXPORT_CANVAS = False
STARTUP_ERROR: str | None = None


def setup() -> None:
    global CAMERA, STARTUP_ERROR

    p5.create_canvas(640, 480)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        CAMERA = p5.create_capture("video", width=640, height=480)
    except BackendCapabilityError as exc:
        STARTUP_ERROR = str(exc)
        CAMERA = None


def draw() -> None:
    p5.background(16, 18, 28)

    if CAMERA is not None:
        frame = CAMERA.read()
        if frame is not None:
            p5.image(frame, 0, 0, p5.width(), p5.height())
            return

    p5.fill(255)
    p5.text_align(p5.CENTER, p5.CENTER)
    p5.text(STARTUP_ERROR or "No camera frame available.", p5.width() / 2, p5.height() / 2)

    if EXPORT_CANVAS and p5.frame_count() == 0:
        p5.save_canvas(str(OUTPUT))


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()

    global EXPORT_CANVAS
    EXPORT_CANVAS = args.headless is not False or args.frames is not None
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)


if __name__ == "__main__":
    main()
