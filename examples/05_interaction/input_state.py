"""Mouse, keyboard, movement deltas, buttons, and touch state access."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/05_interaction/input_state.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


@gs.setup
def setup() -> None:
    gs.create_canvas(620, 360)
    gs.frame_rate(60)


@gs.draw
def draw() -> None:
    gs.background(238, 241, 236)
    position = gs.mouse.position
    x = position.x or 310
    y = position.y or 180

    gs.no_stroke()
    gs.fill(34, 118, 210, 210 if gs.mouse.is_pressed else 130)
    gs.circle(x, y, 54)
    gs.stroke(32, 36, 44)
    gs.line(gs.mouse.previous_position, position)

    gs.no_stroke()
    gs.fill(30, 34, 44)
    gs.text_size(15)
    rows = [
        f"mouse: ({gs.mouse.x:.1f}, {gs.mouse.y:.1f})",
        f"previous: ({gs.mouse.previous_x:.1f}, {gs.mouse.previous_y:.1f})",
        f"moved: ({gs.mouse.moved_x:.1f}, {gs.mouse.moved_y:.1f})",
        f"mouse pressed: {gs.mouse.is_pressed}  button: {gs.mouse.button}",
        f"key pressed: {gs.keyboard.is_pressed}  key: {gs.keyboard.key}  code: {gs.keyboard.code}",
        f"left arrow down: {gs.keyboard.is_down(gs.LEFT_ARROW)}",
        f"touch count: {len(gs.touches())}",
    ]
    for i, row in enumerate(rows):
        gs.text(row, 28, 38 + i * 28)

    save_once(ARGS, gs.current.frame_count, gs.save_canvas)


if __name__ == "__main__":
    gs.run(headless=ARGS.headless, max_frames=ARGS.frames)
