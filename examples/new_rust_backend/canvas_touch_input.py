"""Touch input demo for the Rust canvas backend.

Run:
    uv run python examples/new_rust_backend/canvas_touch_input.py --interactive
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5

OUTPUT = Path("examples/output/new_rust_backend/canvas_touch_input.png")


class CanvasTouchInputDemo(p5.Sketch):
    def __init__(self, *, headless: bool | None = None, export_canvas: bool = False) -> None:
        super().__init__(headless=headless)
        self.export_canvas = export_canvas
        self.points: list[tuple[float, float, float]] = []

    def setup(self) -> None:
        p5.create_canvas(640, 360)
        p5.frame_rate(60)

    def draw(self) -> None:
        p5.background(18, 24, 31)
        p5.no_stroke()
        for index, (x, y, pressure) in enumerate(self.points[-80:]):
            alpha = 60 + min(180, index * 3)
            radius = 12 + pressure * 36
            p5.fill(58, 190, 160, alpha)
            p5.circle(x, y, radius)
        p5.fill(235)
        p5.text_size(18)
        p5.text(f"active touches: {len(p5.touches())}", 24, 34)
        if self.export_canvas and p5.frame_count() == 0:
            p5.save_canvas(str(OUTPUT), overwrite=True)

    def touch_started(self, event: object = None) -> None:
        self._record_touches()

    def touch_moved(self, event: object = None) -> None:
        self._record_touches()

    def touch_ended(self, event: object = None) -> None:
        self._record_touches()

    def _record_touches(self) -> None:
        for touch in p5.touches():
            self.points.append((touch.x, touch.y, touch.pressure or 0.5))


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    demo = CanvasTouchInputDemo(
        headless=args.headless,
        export_canvas=not args.no_save and args.frames is not None and args.frames > 0,
    )
    demo.run(max_frames=args.frames)


if __name__ == "__main__":
    main()
