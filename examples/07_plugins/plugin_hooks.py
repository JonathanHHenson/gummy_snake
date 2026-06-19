"""Install a plugin that observes lifecycle hooks and exposes an API."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import p5
from examples.common import example_parser, save_once
from p5.plugins import Plugin, clear_plugins, install_plugin

OUTPUT = Path("examples/output/07_plugins/plugin_hooks.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()
EVENTS: list[str] = []


class TracePlugin(Plugin):
    name = "trace-example"
    priority = 10

    def install(self, registry) -> None:
        registry.expose_api("trace_label", self.trace_label)
        EVENTS.append("install")

    def before_setup(self, context) -> None:
        del context
        EVENTS.append("before_setup")

    def after_setup(self, context) -> None:
        EVENTS.append(f"after_setup {context.width}x{context.height}")

    def before_draw(self, context) -> None:
        EVENTS.append(f"before_draw {context.frame_count}")

    def after_draw(self, context) -> None:
        EVENTS.append(f"after_draw {context.frame_count}")

    def trace_label(self, context, label: str) -> str:
        value = f"{label}@{context.frame_count}"
        EVENTS.append(value)
        return value


def setup() -> None:
    p5.create_canvas(640, 360)


def draw() -> None:
    label = p5.trace_label("draw")  # type: ignore[attr-defined]
    p5.background(245, 244, 238)
    p5.fill(30, 34, 44)
    p5.text_size(17)
    p5.text(f"plugin API returned: {label}", 34, 42)
    p5.text_size(14)
    for i, event in enumerate(EVENTS[-12:]):
        p5.text(event, 46, 86 + i * 22)
    save_once(ARGS, p5.frame_count(), p5.save_canvas)


if __name__ == "__main__":
    clear_plugins()
    install_plugin(TracePlugin())
    p5.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
    clear_plugins()
