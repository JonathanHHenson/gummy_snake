from __future__ import annotations

import pytest

import gummysnake.rust as rust_acceleration
from gummysnake.core import random as random_module
from gummysnake.rust import _accelerated as original_accelerated
from gummysnake.rust import (
    animated_noise_rgba,
    benchmarks,
    exclusion_blend_rgb,
    exclusion_blend_rgb_python,
    health_check,
    is_acceleration_available,
    noise_3d,
    noise_3d_python,
)


class FakeAccelerated:
    def health_check(self) -> str:
        return "fake-rust"

    def noise3(
        self,
        x: float,
        y: float,
        z: float,
        seed: int,
        octaves: int,
        falloff: float,
    ) -> float:
        assert (x, y, z, seed, octaves, falloff) == (1.0, 2.0, 3.0, 7, 2, 0.25)
        return 0.75

    def exclusion_blend_rgb(self, base: bytes, overlay: bytes) -> bytes:
        assert base == b"\x00\x40"
        assert overlay == b"\xff\x80"
        return b"\x01\x02"

    def animated_noise_rgba(
        self,
        width: int,
        height: int,
        density: float,
        time: float,
        seed: int,
        octaves: int,
        falloff: float,
    ) -> bytes:
        assert (width, height, density, time, seed, octaves, falloff) == (
            2,
            1,
            1.0,
            0.5,
            7,
            2,
            0.25,
        )
        return bytes([1, 2, 3, 255, 4, 5, 6, 255])


def test_health_check_reports_fallback_or_extension() -> None:
    assert health_check() in {"python-fallback", "rust-accelerated"}


def test_wrappers_prefer_accelerated_module_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rust_acceleration, "_accelerated", FakeAccelerated())

    assert is_acceleration_available()
    assert health_check() == "fake-rust"
    assert noise_3d(1, 2, 3, seed=7, octaves=2, falloff=0.25) == 0.75
    assert exclusion_blend_rgb(b"\x00\x40", b"\xff\x80") == b"\x01\x02"
    assert animated_noise_rgba(2, 1, 1, 0.5, seed=7, octaves=2, falloff=0.25) == bytes(
        [1, 2, 3, 255, 4, 5, 6, 255]
    )


def test_monkeypatch_restores_original_acceleration_module() -> None:
    assert rust_acceleration._accelerated is original_accelerated


def test_noise_acceleration_matches_python_reference_for_selected_samples() -> None:
    samples = [
        (0.0, 0.0, 0.0),
        (0.1, 0.2, 0.3),
        (0.5, 0.25, 0.125),
        (-1.25, 2.5, -3.75),
    ]

    for x, y, z in samples:
        expected = noise_3d_python(x, y, z, seed=42, octaves=3, falloff=0.4)
        actual = noise_3d(x, y, z, seed=42, octaves=3, falloff=0.4)
        assert actual == pytest.approx(expected, abs=1e-12)


def test_global_noise_delegates_to_acceleration_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_noise_3d(
        x: float,
        y: float,
        z: float,
        *,
        seed: int,
        octaves: int,
        falloff: float,
    ) -> float:
        calls.append((x, y, z, seed, octaves, falloff))
        return 0.625

    monkeypatch.setattr(random_module, "_noise_3d", fake_noise_3d)
    random_module.noise_seed(12)
    random_module.noise_detail(2, 0.25)

    assert random_module.noise(1, 2, 3) == 0.625
    assert calls == [(1.0, 2.0, 3.0, 12, 2, 0.25)]


def test_exclusion_blend_acceleration_matches_python_reference() -> None:
    base = bytes([0, 64, 128, 255, 10, 20])
    overlay = bytes([255, 128, 64, 0, 50, 200])

    assert exclusion_blend_rgb(base, overlay) == exclusion_blend_rgb_python(base, overlay)


def test_animated_noise_rgba_returns_physical_rgba_buffer() -> None:
    pixels = animated_noise_rgba(3, 2, 2, 0.125, seed=23, octaves=2, falloff=0.5)

    assert len(pixels) == 3 * 2 * 2 * 2 * 4
    assert pixels[3::4] == bytes([255] * (3 * 2 * 2 * 2))


def test_benchmark_smoke_helpers_run_with_or_without_extension() -> None:
    noise_result = benchmarks.benchmark_noise(samples=4)
    blend_result = benchmarks.benchmark_exclusion_blend(width=2, height=2, iterations=2)

    assert noise_result.name == "noise_3d"
    assert noise_result.samples == 4
    assert noise_result.acceleration_available in {True, False}
    assert noise_result.accelerated_seconds >= 0
    assert noise_result.python_seconds >= 0

    assert blend_result.name == "exclusion_blend_rgb"
    assert blend_result.samples == 8
    assert blend_result.accelerated_seconds >= 0
    assert blend_result.python_seconds >= 0
