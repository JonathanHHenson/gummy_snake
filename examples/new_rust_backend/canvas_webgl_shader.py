"""Shader API demo for WEBGL mode on the Rust canvas backend.

The current canvas path accepts shader objects and uniforms on the WEBGL API
surface while rendering through the software-projected 3D path.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import p5

DEFAULT_OUTPUT = Path("examples/output/new_rust_backend/canvas_webgl_shader.png")

VERTEX_SHADER = """
#version 150
in vec3 a_position;
uniform mat4 u_model_view_projection;
void main() {
    gl_Position = u_model_view_projection * vec4(a_position, 1.0);
}
""".strip()

FRAGMENT_SHADER = """
#version 150
uniform float u_time;
uniform float u_scale;
out vec4 fragColor;
void main() {
    fragColor = vec4(abs(sin(u_time)), 0.6, u_scale, 1.0);
}
""".strip()


class CanvasWebGLShaderDemo(p5.Sketch):
    def __init__(
        self,
        *,
        backend: str = p5.CANVAS,
        export_canvas: bool = False,
        output: Path = DEFAULT_OUTPUT,
    ) -> None:
        super().__init__(backend=backend)
        self.export_canvas = export_canvas
        self.output = output
        self.program = p5.create_shader(VERTEX_SHADER, FRAGMENT_SHADER)

    def setup(self) -> None:
        p5.create_canvas(640, 420, p5.WEBGL)
        p5.frame_rate(60)
        p5.no_stroke()
        p5.shader(self.program)
        p5.perspective(math.pi / 3, 640 / 420, 0.1, 2000)

    def draw(self) -> None:
        frame = p5.frame_count()
        p5.background(8, 12, 24)
        p5.camera(math.sin(frame * 0.02) * 220, 80, 380, 0, 0, 0, 0, 1, 0)
        p5.ambient_light(35)
        p5.directional_light(255, 255, 255, -0.4, -0.7, -1.0)
        self.program = p5.create_shader(VERTEX_SHADER, FRAGMENT_SHADER)
        p5.shader(self.program)
        self.program.set_uniform("u_time", frame / 60.0)
        self.program.set_uniform("u_scale", 0.9)

        p5.no_stroke()
        for index in range(96):
            x = (index * 43 + frame * (index % 5 + 1)) % 640
            y = (index * 29 + index * index) % 420
            radius = 4 + index % 9
            p5.fill(60 + index % 120, 120 + index % 90, 240, 180)
            p5.circle(x, y, radius)

        p5.stroke(255, 210, 120, 220)
        p5.stroke_weight(2)
        for index in range(36):
            x = (index * 71 + frame * 2) % 640
            y = (index * 37 + frame * 3) % 420
            p5.line(x - 18, y - 12, x + 18, y + 12)

        if self.export_canvas and p5.frame_count() == 0:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            p5.save_canvas(str(self.output), overwrite=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=p5.CANVAS, choices=[p5.CANVAS, p5.PYGLET, "headless"])
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    export_canvas = not args.no_save and args.frames is not None and args.frames > 0
    demo = CanvasWebGLShaderDemo(
        backend=args.backend,
        export_canvas=export_canvas,
        output=args.output,
    )
    demo.run(max_frames=args.frames)


if __name__ == "__main__":
    main()
