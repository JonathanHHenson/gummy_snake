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
VARIANTS = (
    "dense_primitives",
    "sparse_primitives",
    "cached_images",
    "cached_images_nearest",
    "image_upload_churn",
    "blend_modes",
    "erasing",
    "transformed_images",
    "text_only",
    "pixel_readback_upload",
    "mixed_text_pixels",
    "contours_clipping_tint",
    "asteroids_scene",
    "webgl_3d",
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
            [sys.executable, str(CHILD_RUNNER), variant, str(frames)],
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
