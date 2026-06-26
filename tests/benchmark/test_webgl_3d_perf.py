from __future__ import annotations

import json
import statistics
import sys
import textwrap
from dataclasses import dataclass

import pytest
from benchmark_helpers import run_json_subprocess

FRAMES = 90
REPEATS = 2
MIN_MEAN_FPS = 240.0
VARIANTS = (
    "box",
    "sphere",
    "textured_plane",
    "imported_model",
    "repeated_primitives",
)

CHILD_CODE = textwrap.dedent(
    """
    from __future__ import annotations

    import json
    import math
    import platform
    import sys
    import time
    from pathlib import Path

    import gummysnake as gs

    variant = sys.argv[1]
    frames = int(sys.argv[2])
    start = 0.0
    texture = None
    model = None


    def _texture():
        image = gs.create_image(8, 8)
        pixels = bytearray()
        for y in range(8):
            for x in range(8):
                if (x + y) % 2:
                    pixels.extend((255, 210, 70, 255))
                else:
                    pixels.extend((40, 130, 230, 255))
        image.update_pixels(bytes(pixels))
        return image


    def setup() -> None:
        global start, texture, model
        gs.create_canvas(320, 240, gs.WEBGL)
        gs.frame_rate(10_000)
        gs.no_stroke()
        gs.camera(0, -35, 360, 0, 0, 0, 0, 1, 0)
        gs.perspective(math.pi / 3, 320 / 240, 0.1, 2000)
        texture = _texture()
        model = gs.load_model(Path("examples/assets/teapot.obj"), normalize=True)
        start = time.perf_counter()


    def draw() -> None:
        gs.background(8, 10, 18)
        gs.ambient_light(50)
        gs.directional_light(255, 245, 230, -0.4, -0.7, -1.0)
        if variant == "box":
            gs.ambient_material(80, 170, 255)
            gs.rotate(gs.frame_count() * 0.03)
            gs.box(96)
        elif variant == "sphere":
            gs.normal_material()
            gs.rotate(gs.frame_count() * 0.025)
            gs.sphere(82, 28, 18)
        elif variant == "textured_plane":
            gs.texture(texture)
            gs.rotate(gs.frame_count() * 0.018)
            gs.plane(150, 150)
        elif variant == "imported_model":
            gs.specular_material(220, 170, 255)
            gs.shininess(10)
            gs.scale(72)
            gs.rotate(gs.frame_count() * 0.02)
            gs.model(model)
        elif variant == "repeated_primitives":
            for index in range(12):
                with gs.pushed():
                    gs.translate(-130 + index % 4 * 86, -54 + index // 4 * 62)
                    gs.rotate(index * 0.4 + gs.frame_count() * 0.02)
                    if index % 3 == 0:
                        gs.ambient_material(240, 120, 90)
                        gs.box(38)
                    elif index % 3 == 1:
                        gs.normal_material()
                        gs.sphere(22, 16, 10)
                    else:
                        gs.texture(texture)
                        gs.plane(46, 46)
        else:
            raise ValueError(f"unknown benchmark variant: {variant}")


    gs.run(setup=setup, draw=draw, headless=True, max_frames=frames)
    elapsed = time.perf_counter() - start
    print(
        json.dumps(
            {
                "variant": variant,
                "frames": frames,
                "canvas_size": [320, 240],
                "backend_mode": "headless",
                "python": platform.python_version(),
                "platform": platform.platform(),
                "elapsed": elapsed,
                "fps": frames / max(elapsed, 1e-9),
            }
        )
    )
    """
)


@dataclass(frozen=True)
class WebGLBenchmarkSummary:
    variant: str
    samples: tuple[float, ...]
    metadata: dict[str, object]

    @property
    def mean_fps(self) -> float:
        return statistics.mean(self.samples)


def _run_variant(variant: str) -> WebGLBenchmarkSummary:
    samples: list[float] = []
    metadata: dict[str, object] = {}
    for _ in range(REPEATS):
        payload = run_json_subprocess(
            [sys.executable, "-c", CHILD_CODE, variant, str(FRAMES)],
            f"WEBGL benchmark variant {variant!r}",
        )
        samples.append(float(payload["fps"]))
        metadata = {
            "canvas_size": payload["canvas_size"],
            "backend_mode": payload["backend_mode"],
            "python": payload["python"],
            "platform": payload["platform"],
            "frames": payload["frames"],
        }
    return WebGLBenchmarkSummary(variant, tuple(samples), metadata)


@pytest.mark.benchmark
@pytest.mark.parametrize("variant", VARIANTS)
def test_software_webgl_benchmark_variants(variant: str) -> None:
    summary = _run_variant(variant)
    print(
        f"software_webgl_benchmark {summary.variant}: mean_fps={summary.mean_fps:.2f} "
        f"min_fps={min(summary.samples):.2f} max_fps={max(summary.samples):.2f} "
        f"metadata={json.dumps(summary.metadata, sort_keys=True)}"
    )
    assert summary.mean_fps >= MIN_MEAN_FPS
