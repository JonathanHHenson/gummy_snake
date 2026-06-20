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
FRAMES = 120
REPEATS = 2
MIN_MEAN_FPS = 120.0
VARIANTS = (
    "dense_primitives",
    "sparse_primitives",
    "cached_images",
    "cached_images_nearest",
    "image_upload_churn",
    "mixed_text_pixels",
    "asteroids_scene",
    "webgl_3d",
)
CHILD_CODE = textwrap.dedent(
    """
    from __future__ import annotations

    import json
    import math
    import platform
    import sys
    import time

    import p5
    from p5.rust.canvas import is_canvas_available

    variant = sys.argv[1]
    frames = int(sys.argv[2])
    start = 0.0
    sprites = []
    churn_pixels = b""
    shots = []
    asteroids = []


    def _sprite(width, height, seed):
        pixels = bytearray(width * height * 4)
        cx = (width - 1) / 2
        cy = (height - 1) / 2
        radius = min(width, height) / 2
        for y in range(height):
            for x in range(width):
                offset = (y * width + x) * 4
                distance = math.hypot(x - cx, y - cy)
                if distance > radius:
                    pixels[offset : offset + 4] = b"\\x00\\x00\\x00\\x00"
                    continue
                pixels[offset] = (seed * 41 + x * 5) % 256
                pixels[offset + 1] = (seed * 67 + y * 7) % 256
                pixels[offset + 2] = 160 + (x + y + seed) % 80
                pixels[offset + 3] = 255
        return p5.Image(width, height, bytes(pixels))


    def _reset_asteroids():
        global shots, asteroids
        shots = [
            [360.0, 240.0, math.cos(index * 0.62) * 8.5, math.sin(index * 0.62) * 8.5, index]
            for index in range(14)
        ]
        asteroids = [
            [
                60.0 + (index * 101) % 610,
                50.0 + (index * 71) % 380,
                math.cos(index * 1.7) * (0.8 + index % 3 * 0.22),
                math.sin(index * 1.7) * (0.8 + index % 3 * 0.22),
                24.0 + (index % 4) * 9.0,
                index * 0.37,
            ]
            for index in range(18)
        ]


    def _draw_starfield(count):
        p5.no_stroke()
        for index in range(count):
            x = (index * 97 + p5.frame_count() * (index % 4 + 1)) % 720
            y = (index * 53 + index * index) % 480
            alpha = 110 + (index % 4) * 35
            p5.fill(190, 220, 255, alpha)
            p5.circle(x, y, 1 + index % 3)


    def _draw_primitives(count):
        for index in range(count):
            x = 90 + (index * 83) % 520
            y = 80 + (index * 59) % 280
            with p5.pushed():
                p5.translate(x, y)
                p5.rotate(index * 0.18 + p5.frame_count() * 0.01)
                p5.no_fill()
                p5.stroke(180, 190, 210)
                p5.stroke_weight(2.5)
                p5.ellipse(-18, -14, 52, 64)
                p5.stroke(170, 225, 255, 255)
                p5.fill(36, 116, 220, 245)
                p5.triangle(0, -24, -20, 20, 0, 6)
                p5.triangle(0, -24, 0, 6, 20, 20)


    def _draw_laser_field(count):
        p5.no_fill()
        p5.stroke(100, 200, 255, 240)
        p5.stroke_weight(3)
        for index in range(count):
            sx = 80 + (index * 41) % 560
            sy = 60 + (index * 67) % 360
            with p5.pushed():
                p5.translate(sx, sy)
                p5.rotate(math.pi / 4 + index * 0.1)
                p5.line(0, -18, 0, 18)


    def _draw_image_field(*, mutate):
        global churn_pixels
        p5.image_mode(p5.CENTER)
        for index in range(96):
            image = sprites[index % len(sprites)]
            if mutate and index == 0:
                image.update_pixels(churn_pixels)
            x = 34 + (index * 61 + p5.frame_count() * 3) % 660
            y = 34 + (index * 43 + index * index) % 410
            size = 20 + index % 5 * 5
            with p5.pushed():
                p5.translate(x, y)
                p5.rotate(index * 0.13 + p5.frame_count() * 0.012)
                p5.image(image, 0, 0, size, size)


    def _draw_mixed_text_pixels():
        p5.background(11, 18, 28)
        _draw_starfield(24)
        _draw_primitives(8)
        _draw_image_field(mutate=False)
        pixels = p5.load_pixels()
        for offset in range(0, min(len(pixels), 1024), 16):
            pixels[offset] = (pixels[offset] + 3) % 256
            pixels[offset + 1] = (pixels[offset + 1] + 7) % 256
        p5.update_pixels(pixels)
        p5.fill(240)
        p5.no_stroke()
        p5.text_size(16)
        for index in range(18):
            p5.text_width(f"score {index} frame {p5.frame_count()}")
            p5.text(f"score {index * 125}", 28, 36 + index * 22)


    def _draw_asteroids_scene():
        p5.image_mode(p5.CENTER)
        p5.background(7, 10, 22)
        _draw_starfield(96)
        for shot in shots:
            shot[0] = (shot[0] + shot[2]) % 720
            shot[1] = (shot[1] + shot[3]) % 480
            p5.stroke(120, 220, 255)
            p5.stroke_weight(3)
            p5.line(shot[0], shot[1], shot[0] - shot[2] * 2.2, shot[1] - shot[3] * 2.2)
        for asteroid in asteroids:
            asteroid[0] = (asteroid[0] + asteroid[2]) % 720
            asteroid[1] = (asteroid[1] + asteroid[3]) % 480
            asteroid[5] += 0.025
            with p5.pushed():
                p5.translate(asteroid[0], asteroid[1])
                p5.rotate(asteroid[5])
                p5.image(
                    sprites[int(asteroid[4]) % len(sprites)],
                    0,
                    0,
                    asteroid[4] * 2,
                    asteroid[4] * 2,
                )
                p5.no_fill()
                p5.stroke(190, 200, 220, 170)
                p5.stroke_weight(2)
                p5.circle(0, 0, asteroid[4] * 2.2)
        with p5.pushed():
            p5.translate(360, 240)
            p5.rotate(-math.pi / 2 + math.sin(p5.frame_count() * 0.04) * 0.7)
            p5.image(sprites[0], 0, 0, 88, 64)
            p5.stroke(90, 180, 255)
            p5.line(0, 0, 56, 0)
        p5.fill(245)
        p5.no_stroke()
        p5.text_size(18)
        p5.text(f"wave 4   shots {len(shots)}   rocks {len(asteroids)}", 24, 34)


    def _draw_webgl_3d():
        p5.background(10, 14, 28)
        p5.ambient_light(45)
        p5.directional_light(255, 244, 230, -0.45, -0.7, -1.0)
        p5.point_light(100, 180, 255, 160, -130, 220)

        with p5.pushed():
            p5.translate(-185, 0)
            p5.rotate(p5.frame_count() * 0.035)
            p5.specular_material(240, 150, 90)
            p5.shininess(18)
            p5.box(120)

        with p5.pushed():
            p5.translate(25, 8)
            p5.normal_material()
            p5.sphere(78, 28, 18)

        with p5.pushed():
            p5.translate(225, 24)
            p5.texture(sprites[0])
            p5.rotate(-0.35)
            p5.plane(135, 135)

        with p5.pushed():
            p5.translate(0, 155)
            p5.ambient_material(44, 62, 92)
            p5.plane(650, 160)


    def setup() -> None:
        global start
        global sprites, churn_pixels
        renderer = p5.WEBGL if variant == "webgl_3d" else p5.P2D
        p5.create_canvas(720, 480, renderer)
        p5.frame_rate(10_000)
        if variant == "webgl_3d":
            p5.no_stroke()
            p5.camera(0, -60, 470, 0, 20, 0, 0, 1, 0)
            p5.perspective(math.pi / 3, 720 / 480, 0.1, 4000)
        sprites = [_sprite(48, 48, seed) for seed in range(5)]
        churn_pixels = _sprite(48, 48, 99).to_rgba_bytes()
        if variant == "cached_images_nearest":
            p5.no_smooth()
        _reset_asteroids()
        start = time.perf_counter()


    def draw() -> None:
        p5.background(8, 13, 32)
        if variant == "dense_primitives":
            _draw_starfield(72)
            _draw_primitives(28)
            _draw_laser_field(16)
        elif variant == "sparse_primitives":
            _draw_starfield(12)
            _draw_primitives(6)
            _draw_laser_field(4)
        elif variant == "cached_images":
            _draw_image_field(mutate=False)
        elif variant == "cached_images_nearest":
            _draw_image_field(mutate=False)
        elif variant == "image_upload_churn":
            _draw_image_field(mutate=True)
        elif variant == "mixed_text_pixels":
            _draw_mixed_text_pixels()
        elif variant == "asteroids_scene":
            _draw_asteroids_scene()
        elif variant == "webgl_3d":
            _draw_webgl_3d()
        else:
            raise ValueError(f"unknown benchmark variant: {variant}")


    def main() -> None:
        if not is_canvas_available():
            print(json.dumps({"skipped": True, "reason": "canvas extension unavailable"}))
            return
        p5.run(setup=setup, draw=draw, headless=True, max_frames=frames)
        elapsed = time.perf_counter() - start
        print(
            json.dumps(
                {
                    "variant": variant,
                    "frames": frames,
                    "canvas_size": [720, 480],
                    "pixel_density": 1.0,
                    "backend_mode": "headless",
                    "gpu_available": None,
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "elapsed": elapsed,
                    "fps": frames / max(elapsed, 1e-9),
                }
            )
        )


    if __name__ == "__main__":
        main()
    """
)


@dataclass(frozen=True)
class BenchmarkSummary:
    variant: str
    samples: tuple[float, ...]
    metadata: dict[str, object]

    @property
    def mean_fps(self) -> float:
        return statistics.mean(self.samples)

    @property
    def min_fps(self) -> float:
        return min(self.samples)

    @property
    def max_fps(self) -> float:
        return max(self.samples)


def _run_variant(variant: str, *, frames: int = FRAMES, repeats: int = REPEATS) -> BenchmarkSummary:
    samples: list[float] = []
    metadata: dict[str, object] = {}
    for _ in range(repeats):
        result = subprocess.run(
            [sys.executable, "-c", CHILD_CODE, variant, str(frames)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            raise AssertionError(f"benchmark variant {variant!r} failed\n{detail}")
        stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
        payload = json.loads(stdout_lines[-1])
        if payload.get("skipped"):
            pytest.skip(str(payload["reason"]))
        samples.append(float(payload["fps"]))
        metadata = {
            "canvas_size": payload["canvas_size"],
            "pixel_density": payload["pixel_density"],
            "backend_mode": payload["backend_mode"],
            "gpu_available": payload["gpu_available"],
            "python": payload["python"],
            "platform": payload["platform"],
            "frames": payload["frames"],
        }
    return BenchmarkSummary(variant=variant, samples=tuple(samples), metadata=metadata)


@pytest.mark.benchmark
@pytest.mark.parametrize("variant", VARIANTS)
def test_canvas_benchmark_variants_execute(variant: str) -> None:
    summary = _run_variant(variant)
    print(
        f"benchmark {summary.variant}: mean_fps={summary.mean_fps:.2f} "
        f"min_fps={summary.min_fps:.2f} max_fps={summary.max_fps:.2f} "
        f"metadata={json.dumps(summary.metadata, sort_keys=True)}"
    )
    assert summary.mean_fps >= MIN_MEAN_FPS


@pytest.mark.benchmark
def test_canvas_dense_scene_regression_ratio() -> None:
    sparse = _run_variant("sparse_primitives")
    dense = _run_variant("dense_primitives")
    cached_images = _run_variant("cached_images")
    nearest_images = _run_variant("cached_images_nearest")
    churn_images = _run_variant("image_upload_churn")
    asteroids = _run_variant("asteroids_scene")

    dense_ratio = dense.mean_fps / sparse.mean_fps
    image_ratio = churn_images.mean_fps / cached_images.mean_fps
    sampling_ratio = nearest_images.mean_fps / cached_images.mean_fps
    print(
        f"benchmark ratios: dense/sparse={dense_ratio:.3f} "
        f"image_upload_churn/cached={image_ratio:.3f} "
        f"cached_nearest/cached_linear={sampling_ratio:.3f} "
        f"asteroids_scene_fps={asteroids.mean_fps:.2f}"
    )

    assert sparse.mean_fps >= dense.mean_fps
    assert cached_images.mean_fps >= MIN_MEAN_FPS
    assert nearest_images.mean_fps >= MIN_MEAN_FPS
    assert churn_images.mean_fps >= MIN_MEAN_FPS
    assert asteroids.mean_fps >= MIN_MEAN_FPS
