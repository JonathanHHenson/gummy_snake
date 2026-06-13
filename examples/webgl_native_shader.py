from __future__ import annotations

import math
from argparse import ArgumentParser

import p5_py as p5

VERTEX_SHADER = """
#version 120
uniform float u_scale;
void main() {
    vec4 position = gl_Vertex;
    position.xyz *= u_scale;
    gl_Position = gl_ModelViewProjectionMatrix * position;
}
""".strip()

FRAGMENT_SHADER = """
#version 120
uniform float u_time;
void main() {
    float pulse = 0.5 + 0.5 * sin(u_time * 2.0);
    gl_FragColor = vec4(pulse, 0.35, 1.0 - pulse, 1.0);
}
""".strip()

program = p5.create_shader(VERTEX_SHADER, FRAGMENT_SHADER)


def setup() -> None:
    p5.create_canvas(480, 360, renderer=p5.WEBGL)
    p5.no_stroke()
    p5.camera(0, 0, 220, 0, 0, 0, 0, 1, 0)
    p5.perspective(math.pi / 3, 480 / 360, 0.1, 1000)
    p5.shader(program)


def draw() -> None:
    p5.background(10, 12, 24)
    program.set_uniform("u_time", p5.millis() / 1000.0)
    program.set_uniform("u_scale", 1.0)
    p5.box(120)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--backend", default="pyglet")
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()
    p5.run(setup=setup, draw=draw, backend=args.backend, max_frames=args.frames)
