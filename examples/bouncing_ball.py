"""A simple animated bouncing ball.

Interactive:
    uv run python examples/bouncing_ball.py

Headless smoke run:
    uv run python examples/bouncing_ball.py --headless --frames 5
"""

from __future__ import annotations

import argparse

import p5

x = 80.0
y = 80.0
vx = 4.0
vy = 3.0
radius = 28.0
ground_offset = 15
frame_count = 0
fps_print_interval_ms = 1000.0
last_fps_print_millis = 0.0


def setup() -> None:
    p5.create_canvas(640, 360)
    p5.frame_rate(60)


def draw() -> None:
    global vx, vy, x, y

    p5.background(18, 24, 38)

    x += vx
    y += vy

    if x < radius or x > p5.width() - radius:
        vx *= -1
    if y < radius or y > p5.height() - radius - ground_offset:
        vy *= -1

    p5.no_stroke()
    p5.fill(255, 203, 107)
    p5.circle(x, y, radius * 2)

    p5.stroke(255, 255, 255, 80)
    p5.stroke_weight(2)
    p5.line(0, p5.height() - ground_offset, p5.width(), p5.height() - ground_offset)

    print_fps()


def print_fps() -> None:
    global frame_count, last_fps_print_millis

    frame_count += 1
    now = p5.millis()
    fps_print_delta = now - last_fps_print_millis
    if fps_print_delta >= fps_print_interval_ms:
        fps_sample = 1000 * frame_count / fps_print_delta
        print(f"FPS: {fps_sample:.1f}")
        last_fps_print_millis = now
        frame_count = 0


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()
    p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)


if __name__ == "__main__":
    main()
