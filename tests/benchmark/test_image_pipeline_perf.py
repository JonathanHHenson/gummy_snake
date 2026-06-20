from __future__ import annotations

import statistics
import time

import pytest

import p5


def _sprite(width: int, height: int, seed: int = 0) -> p5.Image:
    pixels = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            offset = (y * width + x) * 4
            pixels[offset] = (seed + x * 3) % 256
            pixels[offset + 1] = (seed + y * 5) % 256
            pixels[offset + 2] = (x + y + seed) % 256
            pixels[offset + 3] = 255
    return p5.Image(width, height, bytes(pixels))


def _time_samples(callback, *, samples: int = 5) -> tuple[float, ...]:
    timings: list[float] = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        callback()
        timings.append((time.perf_counter_ns() - start) / 1_000_000)
    return tuple(timings)


@pytest.mark.benchmark
def test_image_local_operation_benchmarks() -> None:
    base = _sprite(96, 96, 17)
    mask = _sprite(96, 96, 91)

    cases = {
        "copy_region_48": lambda: base.copy(12, 12, 48, 48),
        "resize_96_to_48": lambda: base.copy().resize(48, 48),
        "mask_96": lambda: base.copy().mask(mask),
        "filter_invert_96": lambda: base.copy().filter(p5.INVERT),
        "get_pixel": lambda: base.get(15, 19),
        "set_pixel": lambda: base.copy().set(15, 19, (1, 2, 3, 255)),
    }

    for name, callback in cases.items():
        samples = _time_samples(callback)
        print(
            f"image_operation {name}: mean_ms={statistics.mean(samples):.4f} "
            f"min_ms={min(samples):.4f} max_ms={max(samples):.4f}"
        )


@pytest.mark.benchmark
def test_pixel_buffer_workflow_benchmarks() -> None:
    payload = bytes([10, 20, 30, 255] * (160 * 120))

    def setup() -> None:
        p5.create_canvas(160, 120)
        p5.update_pixels(payload)

    context = p5.run(setup=setup, headless=True, max_frames=0)

    cases = {
        "load_pixels_list": context.load_pixels,
        "load_pixel_bytes": context.load_pixel_bytes,
        "get_pixel_region": lambda: context.get(4, 4, 16, 16),
        "set_pixel_region": lambda: context.set(8, 8, p5.Color(1, 2, 3, 255)),
        "update_pixels_bytes": lambda: context.update_pixels(payload),
        "update_pixels_memoryview": lambda: context.update_pixels(memoryview(payload)),
    }

    for name, callback in cases.items():
        samples = _time_samples(callback)
        print(
            f"pixel_workflow {name}: mean_ms={statistics.mean(samples):.4f} "
            f"min_ms={min(samples):.4f} max_ms={max(samples):.4f}"
        )
