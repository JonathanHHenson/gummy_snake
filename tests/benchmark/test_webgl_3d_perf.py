from __future__ import annotations

import json
import statistics
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRAMES = 90
REPEATS = 2
MIN_MEAN_FPS = 120.0
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

    import p5

    variant = sys.argv[1]
    frames = int(sys.argv[2])
    start = 0.0
    texture = None
    model = None


    def _texture():
        image = p5.create_image(8, 8)
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
        p5.create_canvas(320, 240, p5.WEBGL)
        p5.frame_rate(10_000)
        p5.no_stroke()
        p5.camera(0, -35, 360, 0, 0, 0, 0, 1, 0)
        p5.perspective(math.pi / 3, 320 / 240, 0.1, 2000)
        texture = _texture()
        model = p5.load_model(Path("examples/assets/teapot.obj"), normalize=True)
        start = time.perf_counter()


    def draw() -> None:
        p5.background(8, 10, 18)
        p5.ambient_light(50)
        p5.directional_light(255, 245, 230, -0.4, -0.7, -1.0)
        if variant == "box":
            p5.ambient_material(80, 170, 255)
            p5.rotate(p5.frame_count() * 0.03)
            p5.box(96)
        elif variant == "sphere":
            p5.normal_material()
            p5.rotate(p5.frame_count() * 0.025)
            p5.sphere(82, 28, 18)
        elif variant == "textured_plane":
            p5.texture(texture)
            p5.rotate(p5.frame_count() * 0.018)
            p5.plane(150, 150)
        elif variant == "imported_model":
            p5.specular_material(220, 170, 255)
            p5.shininess(10)
            p5.scale(72)
            p5.rotate(p5.frame_count() * 0.02)
            p5.model(model)
        elif variant == "repeated_primitives":
            for index in range(12):
                with p5.pushed():
                    p5.translate(-130 + index % 4 * 86, -54 + index // 4 * 62)
                    p5.rotate(index * 0.4 + p5.frame_count() * 0.02)
                    if index % 3 == 0:
                        p5.ambient_material(240, 120, 90)
                        p5.box(38)
                    elif index % 3 == 1:
                        p5.normal_material()
                        p5.sphere(22, 16, 10)
                    else:
                        p5.texture(texture)
                        p5.plane(46, 46)
        else:
            raise ValueError(f"unknown benchmark variant: {variant}")


    p5.run(setup=setup, draw=draw, headless=True, max_frames=frames)
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
        result = subprocess.run(
            [sys.executable, "-c", CHILD_CODE, variant, str(FRAMES)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            raise AssertionError(f"WEBGL benchmark variant {variant!r} failed\n{detail}")
        payload = json.loads([line for line in result.stdout.splitlines() if line.strip()][-1])
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
