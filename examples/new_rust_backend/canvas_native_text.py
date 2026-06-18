"""Native canvas text rendering and metrics demo."""

from __future__ import annotations

import argparse
from pathlib import Path

import p5

OUTPUT = Path("examples/output/new_rust_backend/canvas_native_text.png")


class CanvasNativeTextDemo(p5.Sketch):
    def __init__(self, *, headless: bool | None = None, export_canvas: bool = False) -> None:
        super().__init__(headless=headless)
        self.export_canvas = export_canvas

    def setup(self) -> None:
        p5.create_canvas(720, 420, pixel_density=1.5)
        p5.frame_rate(60)

    def draw(self) -> None:
        p5.background(245, 247, 250)
        p5.text_size(42)
        p5.text_align(p5.LEFT, p5.BASELINE)
        label = "Native canvas text"
        width = p5.text_width(label)
        ascent = p5.text_ascent()
        descent = p5.text_descent()
        x = 48
        y = 128
        p5.no_stroke()
        p5.fill(32, 42, 54)
        p5.text(label, x, y)
        p5.fill(58, 190, 160, 90)
        p5.rect(x, y - ascent, width, ascent + descent)
        p5.fill(36, 94, 168)
        p5.text_size(22)
        p5.text(f"width {width:.1f}  ascent {ascent:.1f}  descent {descent:.1f}", 48, 210)
        p5.push()
        p5.translate(420, 300)
        p5.rotate(0.22)
        p5.fill(170, 72, 85)
        p5.text_size(30)
        p5.text_align(p5.CENTER, p5.CENTER)
        p5.text("transformed", 0, 0)
        p5.pop()
        if self.export_canvas and p5.frame_count() == 0:
            p5.save_canvas(str(OUTPUT), overwrite=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    demo = CanvasNativeTextDemo(
        headless=args.headless,
        export_canvas=not args.no_save and args.frames is not None and args.frames > 0,
    )
    demo.run(max_frames=args.frames)


if __name__ == "__main__":
    main()
