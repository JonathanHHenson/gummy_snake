"""setup/draw lifecycle controls, resize_canvas, no_loop, loop, and redraw."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/05_interaction/lifecycle_controls.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
DRAWS = 0
MANUAL_REDRAWS = 0
AUTO_PAUSED = False


@p5.setup
def setup() -> None:
    p5.create_canvas(520, 300)
    p5.frame_rate(12)


@p5.draw
def draw() -> None:
    global AUTO_PAUSED, DRAWS
    DRAWS += 1
    if p5.current.frame_count == 4:
        p5.resize_canvas(620, 340)
    if p5.current.frame_count == 8 and not AUTO_PAUSED and ARGS.headless is False:
        AUTO_PAUSED = True
        p5.no_loop()

    p5.background(29, 33, 45)
    p5.fill(240)
    p5.text_size(16)
    p5.text(f"canvas: {p5.current.width} x {p5.current.height}", 30, 44)
    p5.text(f"frame: {p5.current.frame_count}  draw calls: {DRAWS}", 30, 72)
    p5.text(f"looping: {p5.current.is_looping}  manual redraws: {MANUAL_REDRAWS}", 30, 100)
    p5.text("Auto-pauses at frame 8. Click redraws once. Press L to loop, P to pause.", 30, 130)

    with p5.style(stroke=None):
        for i in range(p5.current.frame_count % 12 + 1):
            p5.fill(60 + i * 12, 180, 160)
            p5.circle(46 + i * 44, 238, 24)

    save_once(ARGS, p5.current.frame_count, p5.save_canvas)


@p5.on(p5.MOUSE_PRESSED)
def mouse_pressed(_event) -> None:
    global MANUAL_REDRAWS
    MANUAL_REDRAWS += 1
    p5.redraw()


@p5.on(p5.KEY_PRESSED)
def key_pressed(event) -> None:
    if event.matches("l"):
        p5.loop()
    if event.matches("p"):
        p5.no_loop()


if __name__ == "__main__":
    p5.run(headless=ARGS.headless, max_frames=ARGS.frames)
