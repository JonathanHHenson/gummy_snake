"""Example plugin showing lifecycle hooks and runtime API extension."""

from __future__ import annotations

import argparse

import p5
from p5.plugins import Plugin, install_plugin, uninstall_plugin


class GridPlugin(Plugin):
    name = "grid"
    priority = 20

    def install(self, registry) -> None:
        registry.expose_api("draw_grid", self.draw_grid)

    def before_draw(self, context) -> None:
        context.stroke(230)
        context.stroke_weight(1)

    def draw_grid(self, context, step: int = 20) -> None:
        for x in range(0, context.width + 1, step):
            context.line(x, 0, x, context.height)
        for y in range(0, context.height + 1, step):
            context.line(0, y, context.width, y)


install_plugin(GridPlugin())


def setup() -> None:
    p5.create_canvas(240, 180)
    p5.no_stroke()


def draw() -> None:
    p5.background(250)
    p5.draw_grid(20)
    p5.fill(255, 80, 80)
    p5.circle(120, 90, 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", dest="headless", action="store_true")
    mode.add_argument("--interactive", dest="headless", action="store_false")
    parser.set_defaults(headless=None)
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()
    try:
        p5.run(setup=setup, draw=draw, headless=args.headless, max_frames=args.frames)
    finally:
        uninstall_plugin("grid")
