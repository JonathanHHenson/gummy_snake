from __future__ import annotations

import math
from argparse import ArgumentParser

import p5
from p5.exceptions import BackendCapabilityError, ShaderCompilationError

VERTEX_SHADER = """
#version 150
in vec3 a_position;
uniform float u_scale;
uniform float u_time;
out vec3 v_position;

void main() {
    float angle_y = 0.95 + u_time * 0.9;
    float angle_x = -0.95 + u_time * 0.6;
    float cy = cos(angle_y);
    float sy = sin(angle_y);
    float cx = cos(angle_x);
    float sx = sin(angle_x);

    mat3 rot_y = mat3(
        cy, 0.0, sy,
        0.0, 1.0, 0.0,
        -sy, 0.0, cy
    );
    mat3 rot_x = mat3(
        1.0, 0.0, 0.0,
        0.0, cx, -sx,
        0.0, sx, cx
    );
    mat3 rotation = rot_y * rot_x;

    vec3 position = rotation * (a_position * u_scale);
    v_position = position;

    float aspect = 480.0 / 360.0;
    float f = 1.0 / tan(radians(60.0) * 0.5);
    float camera_distance = 220.0;
    float depth = camera_distance - position.z;
    float inv_depth = 1.0 / max(depth, 90.0);
    float ndc_x = (f / aspect) * position.x * inv_depth;
    float ndc_y = f * position.y * inv_depth;
    float ndc_z = clamp(position.z / camera_distance, -0.75, 0.75);

    gl_Position = vec4(ndc_x, ndc_y, ndc_z, 1.0);
}
""".strip()

FRAGMENT_SHADER = """
#version 150
uniform float u_time;
in vec3 v_position;
out vec4 fragColor;
void main() {
    vec3 dx = dFdx(v_position);
    vec3 dy = dFdy(v_position);
    vec3 normal = normalize(cross(dx, dy));
    if (!gl_FrontFacing) {
        normal = -normal;
    }

    vec3 light_dir = normalize(vec3(-0.45, 0.7, 0.9));
    vec3 view_dir = normalize(vec3(0.0, 0.0, 1.0) - v_position * 0.0025);
    vec3 half_vec = normalize(light_dir + view_dir);

    float diffuse = max(dot(normal, light_dir), 0.0);
    float specular = pow(max(dot(normal, half_vec), 0.0), 24.0);
    float pulse = 0.5 + 0.5 * sin(u_time * 2.0);
    vec3 base = vec3(pulse, 0.35, 1.0 - pulse);
    vec3 ambient = base * 0.25;
    vec3 lit = ambient + base * diffuse * 0.85 + vec3(1.0) * specular * 0.35;
    fragColor = vec4(lit, 1.0);
}
""".strip()

program = p5.create_shader(VERTEX_SHADER, FRAGMENT_SHADER)
SHADER_ERROR: str | None = None


def setup() -> None:
    global SHADER_ERROR

    p5.create_canvas(480, 360, renderer=p5.WEBGL)
    p5.no_stroke()
    p5.camera(0, 0, 220, 0, 0, 0, 0, 1, 0)
    p5.perspective(math.pi / 3, 480 / 360, 0.1, 1000)
    try:
        p5.shader(program)
    except (BackendCapabilityError, ShaderCompilationError) as exc:
        SHADER_ERROR = str(exc)


def draw() -> None:
    p5.background(10, 12, 24)
    if SHADER_ERROR is not None:
        p5.fill(240)
        p5.text_size(14)
        p5.text("Native shader rendering is unavailable on this system.", 24, 48)
        p5.text(SHADER_ERROR, 24, 76)
        p5.no_fill()
        p5.stroke(160, 180, 255)
        p5.box(120)
        return
    program.set_uniform("u_time", p5.millis() / 1000.0)
    program.set_uniform("u_scale", 1.0)
    p5.box(120)


if __name__ == "__main__":
    parser = ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)
