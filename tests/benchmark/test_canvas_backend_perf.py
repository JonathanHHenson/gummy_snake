from __future__ import annotations

import json
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHILD_RUNNER = Path(__file__).with_name("canvas_backend_perf_child.py")
FRAMES = 120
REPEATS = 2
MIN_MEAN_FPS = 240.0
BENCHMARK_MODE = "interactive"
VARIANTS = (
    "dense_primitives",
    "sparse_primitives",
    "stress_primitives_10k",
    "cached_images",
    "cached_images_nearest",
    "stress_sprites_10k",
    "stress_sprites_50k",
    "image_upload_churn",
    "blend_modes",
    "erasing",
    "transformed_images",
    "text_only",
    "stress_text_1k",
    "stress_sprite_text_overlay",
    "pixel_readback_upload",
    "mixed_text_pixels",
    "contours_clipping_tint",
    "asteroids_scene",
    "webgl_3d",
)
STRESS_FPS_TARGETS = {
    "stress_primitives_10k": 60.0,
    "stress_sprites_10k": 60.0,
    "stress_sprites_50k": 60.0,
}


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


def _run_variant(
    variant: str,
    *,
    frames: int = FRAMES,
    repeats: int = REPEATS,
    mode: str = BENCHMARK_MODE,
) -> BenchmarkSummary:
    samples: list[float] = []
    metadata: dict[str, object] = {}
    for _ in range(repeats):
        result = subprocess.run(
            [sys.executable, str(CHILD_RUNNER), variant, str(frames), mode],
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
            "metrics": payload["metrics"],
            "python": payload["python"],
            "platform": payload["platform"],
            "frames": payload["frames"],
        }
    return BenchmarkSummary(variant=variant, samples=tuple(samples), metadata=metadata)


@pytest.mark.benchmark
@pytest.mark.parametrize("variant", VARIANTS)
def test_canvas_interactive_benchmark_variants_execute(variant: str) -> None:
    summary = _run_variant(variant)
    print(
        f"benchmark {summary.variant}: mean_fps={summary.mean_fps:.2f} "
        f"min_fps={summary.min_fps:.2f} max_fps={summary.max_fps:.2f} "
        f"metadata={json.dumps(summary.metadata, sort_keys=True)}"
    )
    assert summary.mean_fps >= STRESS_FPS_TARGETS.get(variant, MIN_MEAN_FPS)


@pytest.mark.benchmark
@pytest.mark.high_count_benchmark
def test_canvas_high_count_primitive_benchmarks() -> None:
    stress_10k = _run_variant("stress_primitives_10k")
    print(
        f"benchmark {stress_10k.variant}: mean_fps={stress_10k.mean_fps:.2f} "
        f"min_fps={stress_10k.min_fps:.2f} max_fps={stress_10k.max_fps:.2f} "
        f"metadata={json.dumps(stress_10k.metadata, sort_keys=True)}"
    )
    if stress_10k.mean_fps < 60.0:
        pytest.skip("50k primitive benchmark is gated until 10k primitives baseline at 60 FPS.")

    stress_50k = _run_variant("stress_primitives_50k")
    print(
        f"benchmark {stress_50k.variant}: mean_fps={stress_50k.mean_fps:.2f} "
        f"min_fps={stress_50k.min_fps:.2f} max_fps={stress_50k.max_fps:.2f} "
        f"metadata={json.dumps(stress_50k.metadata, sort_keys=True)}"
    )
    if stress_50k.mean_fps < 30.0:
        pytest.skip("100k primitive benchmark is gated until 50k primitives baseline at 30 FPS.")

    stress_100k = _run_variant("stress_primitives_100k")
    print(
        f"benchmark {stress_100k.variant}: mean_fps={stress_100k.mean_fps:.2f} "
        f"min_fps={stress_100k.min_fps:.2f} max_fps={stress_100k.max_fps:.2f} "
        f"metadata={json.dumps(stress_100k.metadata, sort_keys=True)}"
    )


@pytest.mark.benchmark
def test_canvas_interactive_dense_scene_regression_ratio() -> None:
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
