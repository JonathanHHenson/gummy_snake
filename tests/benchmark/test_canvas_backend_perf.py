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
VARIANTS = (
    "asteroids",
    "dense_primitives",
    "sparse_primitives",
)
CHILD_CODE = textwrap.dedent(
    """
    from __future__ import annotations

    import json
    import math
    import sys
    import time

    import p5
    from p5.rust.canvas import is_canvas_available

    from examples.new_rust_backend.canvas_asteroids import AsteroidsDemo

    variant = sys.argv[1]
    frames = int(sys.argv[2])
    start = 0.0


    def setup() -> None:
        global start
        if variant == "asteroids":
            demo.setup()
        else:
            p5.create_canvas(720, 480)
            p5.frame_rate(10_000)
        start = time.perf_counter()


    def draw() -> None:
        if variant == "asteroids":
            demo.draw()
            return

        p5.background(8, 13, 32)
        p5.no_stroke()
        stars = 72 if variant == "dense_primitives" else 12
        for index in range(stars):
            x = (index * 97 + p5.frame_count() * (index % 4 + 1)) % 720
            y = (index * 53 + index * index) % 480
            alpha = 110 + (index % 4) * 35
            p5.fill(190, 220, 255, alpha)
            p5.circle(x, y, 1 + index % 3)

        count = 28 if variant == "dense_primitives" else 6
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

        p5.no_fill()
        p5.stroke(100, 200, 255, 240)
        p5.stroke_weight(3)
        shots = 16 if variant == "dense_primitives" else 4
        for index in range(shots):
            sx = 80 + (index * 41) % 560
            sy = 60 + (index * 67) % 360
            with p5.pushed():
                p5.translate(sx, sy)
                p5.rotate(math.pi / 4 + index * 0.1)
                p5.line(0, -18, 0, 18)


    def main() -> None:
        if not is_canvas_available():
            print(json.dumps({"skipped": True, "reason": "canvas extension unavailable"}))
            return
        global demo
        demo = AsteroidsDemo(export_canvas=False)
        p5.run(setup=setup, draw=draw, headless=True, max_frames=frames)
        elapsed = time.perf_counter() - start
        print(
            json.dumps(
                {
                    "variant": variant,
                    "frames": frames,
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
    return BenchmarkSummary(variant=variant, samples=tuple(samples))


@pytest.mark.benchmark
@pytest.mark.parametrize("variant", VARIANTS)
def test_canvas_benchmark_variants_execute(variant: str) -> None:
    summary = _run_variant(variant)
    print(
        f"benchmark {summary.variant}: mean_fps={summary.mean_fps:.2f} "
        f"min_fps={summary.min_fps:.2f} max_fps={summary.max_fps:.2f}"
    )
    assert summary.mean_fps > 0


@pytest.mark.benchmark
def test_canvas_dense_scene_regression_ratio() -> None:
    sparse = _run_variant("sparse_primitives")
    dense = _run_variant("dense_primitives")
    asteroids = _run_variant("asteroids")

    dense_ratio = dense.mean_fps / sparse.mean_fps
    print(
        f"benchmark ratios: dense/sparse={dense_ratio:.3f} asteroids_fps={asteroids.mean_fps:.2f}"
    )

    assert sparse.mean_fps >= dense.mean_fps
    assert dense.mean_fps >= 50.0
    assert asteroids.mean_fps >= 80.0
