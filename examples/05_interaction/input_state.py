"""Mouse, keyboard, movement deltas, buttons, and touch state access."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/05_interaction/input_state.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()


def setup() -> None:
    p5.create_canvas(620, 360)
    p5.frame_rate(60)


def draw() -> None:
    p5.background(238, 241, 236)
    x = p5.mouse_x() or 310
    y = p5.mouse_y() or 180

    p5.no_stroke()
    p5.fill(34, 118, 210, 210 if p5.mouse_is_pressed() else 130)
    p5.circle(x, y, 54)
    p5.stroke(32, 36, 44)
    p5.line(p5.pmouse_x(), p5.pmouse_y(), x, y)

    p5.no_stroke()
    p5.fill(30, 34, 44)
    p5.text_size(15)
    rows = [
        f"mouse: ({p5.mouse_x():.1f}, {p5.mouse_y():.1f})",
        f"previous: ({p5.pmouse_x():.1f}, {p5.pmouse_y():.1f})",
        f"moved: ({p5.moved_x():.1f}, {p5.moved_y():.1f})",
        f"mouse pressed: {p5.mouse_is_pressed()}  button: {p5.mouse_button()}",
        f"key pressed: {p5.key_is_pressed()}  key: {p5.key()}  code: {p5.key_code()}",
        f"left arrow down: {p5.key_is_down(p5.LEFT_ARROW)}",
        f"touch count: {len(p5.touches())}",
    ]
    for i, row in enumerate(rows):
        p5.text(row, 28, 38 + i * 28)

    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    p5.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
