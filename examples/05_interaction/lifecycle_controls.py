"""setup/draw lifecycle controls, resize_canvas, no_loop, loop, and redraw."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/05_interaction/lifecycle_controls.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
DRAWS = 0
MANUAL_REDRAWS = 0
AUTO_PAUSED = False


@gs.setup
def setup() -> None:
    gs.create_canvas(520, 300)
    gs.frame_rate(12)


@gs.draw
def draw() -> None:
    global AUTO_PAUSED, DRAWS
    DRAWS += 1
    if gs.current.frame_count == 4:
        gs.resize_canvas(620, 340)
    if gs.current.frame_count == 8 and not AUTO_PAUSED and ARGS.headless is False:
        AUTO_PAUSED = True
        gs.no_loop()

    gs.background(29, 33, 45)
    gs.fill(240)
    gs.text_size(16)
    gs.text(f"canvas: {gs.current.width} x {gs.current.height}", 30, 44)
    gs.text(f"frame: {gs.current.frame_count}  draw calls: {DRAWS}", 30, 72)
    gs.text(f"looping: {gs.current.is_looping}  manual redraws: {MANUAL_REDRAWS}", 30, 100)
    gs.text("Auto-pauses at frame 8. Click redraws once. Press L to loop, P to pause.", 30, 130)

    with gs.style(stroke=None):
        for i in range(gs.current.frame_count % 12 + 1):
            gs.fill(60 + i * 12, 180, 160)
            gs.circle(46 + i * 44, 238, 24)

    save_once(ARGS, gs.current.frame_count, gs.save_canvas)


@gs.on(gs.MOUSE_PRESSED)
def mouse_pressed(_event) -> None:
    global MANUAL_REDRAWS
    MANUAL_REDRAWS += 1
    gs.redraw()


@gs.on(gs.KEY_PRESSED)
def key_pressed(event) -> None:
    if event.matches("l"):
        gs.loop()
    if event.matches("p"):
        gs.no_loop()


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
