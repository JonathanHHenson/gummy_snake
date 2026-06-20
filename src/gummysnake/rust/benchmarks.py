"""Small local benchmarks for optional Rust acceleration targets."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

from gummysnake.rust import (
    exclusion_blend_rgb,
    exclusion_blend_rgb_python,
    is_acceleration_available,
    noise_3d,
    noise_3d_python,
)


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    name: str
    samples: int
    accelerated_seconds: float
    python_seconds: float
    acceleration_available: bool

    @property
    def speedup(self) -> float | None:
        if self.accelerated_seconds <= 0:
            return None
        return self.python_seconds / self.accelerated_seconds


def benchmark_noise(samples: int = 2_000) -> BenchmarkResult:
    """Time the selected procedural noise path against the Python fallback."""

    coords = [
        (index * 0.017, index * 0.013, index * 0.011)
        for index in range(_validate_positive_samples(samples))
    ]

    def accelerated() -> float:
        return sum(noise_3d(x, y, z, seed=42, octaves=4, falloff=0.5) for x, y, z in coords)

    def python() -> float:
        return sum(noise_3d_python(x, y, z, seed=42, octaves=4, falloff=0.5) for x, y, z in coords)

    accelerated_seconds = _time(accelerated)
    python_seconds = _time(python)
    return BenchmarkResult(
        name="noise_3d",
        samples=len(coords),
        accelerated_seconds=accelerated_seconds,
        python_seconds=python_seconds,
        acceleration_available=is_acceleration_available(),
    )


def benchmark_exclusion_blend(
    width: int = 256, height: int = 256, iterations: int = 25
) -> BenchmarkResult:
    """Time the selected packed RGB exclusion blend path."""

    width = _validate_positive_samples(width)
    height = _validate_positive_samples(height)
    iterations = _validate_positive_samples(iterations)
    pixel_bytes = width * height * 3
    base = bytes((index * 37 + 11) % 256 for index in range(pixel_bytes))
    overlay = bytes((index * 17 + 83) % 256 for index in range(pixel_bytes))

    def accelerated() -> int:
        checksum = 0
        for _ in range(iterations):
            checksum += exclusion_blend_rgb(base, overlay)[0]
        return checksum

    def python() -> int:
        checksum = 0
        for _ in range(iterations):
            checksum += exclusion_blend_rgb_python(base, overlay)[0]
        return checksum

    accelerated_seconds = _time(accelerated)
    python_seconds = _time(python)
    return BenchmarkResult(
        name="exclusion_blend_rgb",
        samples=width * height * iterations,
        accelerated_seconds=accelerated_seconds,
        python_seconds=python_seconds,
        acceleration_available=is_acceleration_available(),
    )


def run_benchmarks() -> list[BenchmarkResult]:
    return [benchmark_noise(), benchmark_exclusion_blend()]


def _time(func: Callable[[], object]) -> float:
    start = perf_counter()
    func()
    return perf_counter() - start


def _validate_positive_samples(value: int) -> int:
    value = int(value)
    if value < 1:
        msg = "benchmark sizes must be positive."
        raise ValueError(msg)
    return value


def _format_result(result: BenchmarkResult) -> str:
    speedup = "n/a" if result.speedup is None else f"{result.speedup:.2f}x"
    backend = "rust" if result.acceleration_available else "python fallback"
    return (
        f"{result.name}: samples={result.samples} backend={backend} "
        f"accelerated={result.accelerated_seconds:.6f}s "
        f"python={result.python_seconds:.6f}s speedup={speedup}"
    )


if __name__ == "__main__":
    for benchmark in run_benchmarks():
        print(_format_result(benchmark))
