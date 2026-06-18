"""Vector, random, noise, and math helper demo.

Interactive:
    uv run python examples/vector_noise_flow.py

Headless/export:
    uv run python examples/vector_noise_flow.py --headless --frames 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

import p5

OUTPUT = Path("examples/output/vector_noise_flow.png")
EXPORT_CANVAS = False
PARTICLES: list[dict[str, p5.Vector | p5.Color]] = []


def random_float(maximum: float) -> float:
    value = p5.random(maximum)
    assert isinstance(value, int | float)
    return float(value)


def setup() -> None:
    p5.create_canvas(720, 420)
    p5.frame_rate(30)
    p5.angle_mode(p5.DEGREES)
    p5.random_seed(7)
    p5.noise_seed(11)
    p5.noise_detail(4, 0.55)

    PARTICLES.clear()
    for _ in range(180):
        PARTICLES.append(
            {
                "position": p5.create_vector(random_float(p5.width()), random_float(p5.height())),
                "color": p5.color(
                    p5.random(40, 210), p5.random(120, 255), p5.random(180, 255), 150
                ),
            }
        )


def draw() -> None:
    p5.background(9, 14, 28)
    p5.no_fill()
    p5.stroke_weight(1.6)

    time = p5.frame_count() * 0.01
    for particle in PARTICLES:
        position = particle["position"]
        assert isinstance(position, p5.Vector)
        color = particle["color"]
        assert isinstance(color, p5.Color)

        angle = p5.map_value(
            p5.noise(position.x * 0.008, position.y * 0.008, time),
            0,
            1,
            -40,
            400,
        )
        velocity = p5.Vector.from_angle(angle, 2.4)
        previous = position.copy()
        position.add(velocity).add(p5.Vector.from_angle(angle + 90, p5.sin(angle) * 0.25))

        if position.x < 0 or position.x > p5.width() or position.y < 0 or position.y > p5.height():
            position.set(random_float(p5.width()), random_float(p5.height()))
            previous = position.copy()

        p5.stroke(color)
        p5.line(previous.x, previous.y, position.x, position.y)

    draw_frame_badge()

    if EXPORT_CANVAS and p5.frame_count() == 0:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        p5.save_canvas(str(OUTPUT))


def draw_frame_badge() -> None:
    p5.no_stroke()
    p5.fill(255, 255, 255, 80)
    p5.circle(34, 34, 24 + p5.sin(p5.frame_count() * 8) * 6)
    p5.fill(255, 255, 255, 160)
    p5.rect(54, 24, p5.constrain(p5.frame_count() * 4, 8, 180), 12)


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()
    global EXPORT_CANVAS
    EXPORT_CANVAS = args.headless is not False or args.frames is not None
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)


if __name__ == "__main__":
    main()
