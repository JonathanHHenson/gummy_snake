"""WEBGL primitives and model demo for the Rust canvas backend.

Run interactively:
    uv run python examples/new_rust_backend/canvas_webgl_primitives.py

Compare with canvas:
    uv run python examples/new_rust_backend/canvas_webgl_primitives.py --interactive

Run/export a bounded preview:
    uv run python examples/new_rust_backend/canvas_webgl_primitives.py --frames 1
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import p5

DEFAULT_OUTPUT = Path("examples/output/new_rust_backend/canvas_webgl_primitives.png")


class CanvasWebGLPrimitivesDemo(p5.Sketch):
    def __init__(
        self,
        *,
        headless: bool | None = None,
        export_canvas: bool = False,
        output: Path = DEFAULT_OUTPUT,
    ) -> None:
        super().__init__(headless=headless)
        self.export_canvas = export_canvas
        self.output = output
        self.teapot = p5.load_model(Path("examples/assets/teapot.obj"), normalize=True)

    def setup(self) -> None:
        p5.create_canvas(760, 500, p5.WEBGL)
        p5.frame_rate(60)
        p5.no_stroke()
        p5.perspective(math.pi / 3, 760 / 500, 0.1, 2000)

    def draw(self) -> None:
        frame = p5.frame_count()
        p5.background(10, 14, 26)
        p5.camera(
            math.sin(frame * 0.018) * 260,
            110 + math.sin(frame * 0.013) * 30,
            420,
            0,
            0,
            0,
            0,
            1,
            0,
        )
        p5.ambient_light(40)
        p5.directional_light(255, 245, 220, -0.35, -0.7, -1.0)
        p5.point_light(80, 180, 255, math.sin(frame * 0.04) * 180, -100, 160)

        p5.normal_material()
        p5.box(120)

        p5.specular_material(220, 170, 255)
        p5.shininess(12)
        p5.sphere(82, 30, 18)

        p5.ambient_material(120, 220, 190)
        p5.model(self.teapot)

        if self.export_canvas and p5.frame_count() == 0:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            p5.save_canvas(str(self.output), overwrite=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    export_canvas = not args.no_save and args.frames is not None and args.frames > 0
    demo = CanvasWebGLPrimitivesDemo(
        headless=args.headless,
        export_canvas=export_canvas,
        output=args.output,
    )
    demo.run(max_frames=args.frames)


if __name__ == "__main__":
    main()
