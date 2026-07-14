"""Offscreen graphics, framebuffer targets, and storage-buffer compute."""

from __future__ import annotations

import math
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/03_assets/offscreen_graphics_compute.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

CONTEXT_INFO: Mapping[str, object] = {}
BAR_VALUES: tuple[float, ...] = ()
GRAPHICS: gs.Graphics | None = None
FRAMEBUFFER: gs.Framebuffer | None = None

SMOOTH_BARS_WGSL = """
@group(0) @binding(0) var<storage, read_write> source: array<f32>;
@group(0) @binding(1) var<storage, read_write> bars: array<f32>;

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let count = arrayLength(&source);
    let index = gid.x;
    if index >= count {
        return;
    }
    let previous_index = (index + count - 1u) % count;
    let next_index = (index + 1u) % count;
    let smoothed = source[previous_index] * 0.25
        + source[index] * 0.5
        + source[next_index] * 0.25;
    bars[index] = (smoothed + 1.0) * 0.5;
}
"""


def _draw_bars(target: gs.Graphics | gs.Framebuffer, values: tuple[float, ...]) -> None:
    drawing = target.drawing
    drawing.background(13, 18, 30)
    drawing.no_stroke()
    bar_width = target.width / len(values)
    for index, value in enumerate(values):
        hue = index / max(1, len(values) - 1)
        height = value * (target.height - 34)
        drawing.fill(60 + hue * 160, 120 + value * 100, 255 - hue * 80)
        drawing.rect(index * bar_width + 2, target.height - height - 14, bar_width * 0.74, height)
    drawing.stroke(95, 110, 140)
    drawing.no_fill()
    drawing.rect(0, 0, target.width, target.height)


def setup() -> None:
    global BAR_VALUES, CONTEXT_INFO, FRAMEBUFFER, GRAPHICS
    gs.create_canvas(760, 420)
    CONTEXT_INFO = gs.webgpu_context()

    source_values = [math.sin(index * 0.33) * math.cos(index * 0.07) for index in range(48)]
    source = gs.create_storage_buffer(source_values)
    bars = gs.create_storage_buffer(len(source_values))
    shader = gs.create_compute_shader(source=SMOOTH_BARS_WGSL, label="smooth-bars")
    gs.dispatch_compute(shader, len(source_values), source=source, bars=bars)
    BAR_VALUES = tuple(float(value) for value in gs.read_storage_buffer(bars))

    GRAPHICS = gs.create_graphics(360, 220, pixel_density=1)
    FRAMEBUFFER = gs.create_framebuffer(240, 160, pixel_density=1, depth=False)
    _draw_bars(GRAPHICS, BAR_VALUES)
    _draw_bars(FRAMEBUFFER, tuple(reversed(BAR_VALUES[:32])))


def draw() -> None:
    gs.background(18, 23, 35)
    gs.no_stroke()
    gs.fill(245)
    gs.text_size(22)
    gs.text("Offscreen graphics + compute", 32, 40)
    gs.text_size(14)
    gs.text(
        f"compute backend: {CONTEXT_INFO.get('backend')} | "
        f"storage buffers: {CONTEXT_INFO.get('storage_buffers')} | "
        f"browser context: {CONTEXT_INFO.get('browser_context')}",
        32,
        68,
    )
    gs.text(f"dispatched {len(BAR_VALUES)} work items into a StorageBuffer", 32, 92)

    if GRAPHICS is not None:
        gs.image(GRAPHICS, 32, 124)
        gs.fill(210)
        gs.text("create_graphics(): reusable offscreen drawing surface", 32, 366)

    if FRAMEBUFFER is not None:
        gs.image(FRAMEBUFFER.snapshot(), 482, 154)
        gs.fill(210)
        gs.text(
            f"create_framebuffer(depth={FRAMEBUFFER.depth}) snapshot composited on canvas",
            392,
            340,
        )

    gs.stroke(255, 190, 90)
    gs.no_fill()
    gs.rect(28, 120, 368, 228)
    gs.rect(478, 150, 248, 168)

    save_once(ARGS, gs.frame_count(), gs.save_canvas)


if __name__ == "__main__":
    gs.run(setup=setup, draw=draw, headless=ARGS.headless, max_frames=ARGS.frames)
