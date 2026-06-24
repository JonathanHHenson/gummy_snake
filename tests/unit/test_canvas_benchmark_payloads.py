from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmark"


def _load_benchmark_module(name: str) -> ModuleType:
    path = BENCHMARK_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load benchmark helper module {name!r} from {path!s}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


canvas_backend_perf_scenes = _load_benchmark_module("canvas_backend_perf_scenes")
canvas_backend_perf_child = _load_benchmark_module("canvas_backend_perf_child")
_flatten_metrics = cast(Any, canvas_backend_perf_child)._flatten_metrics
draw_scene = cast(Any, canvas_backend_perf_scenes).draw_scene
setup_scene = cast(Any, canvas_backend_perf_scenes).setup_scene


def test_canvas_benchmark_metrics_flatten_native_counters() -> None:
    metrics = _flatten_metrics(
        {
            "gpu_draws": 3,
            "pixel_readbacks": 1,
            "native": {
                "gpu_draws": 9,
                "gpu_primitive_batches": 4,
                "gpu_image_batches": 2,
                "texture_cache_hits": 7,
                "text_cache_hits": 5,
                "frames_presented": 8,
            },
        }
    )

    assert metrics["gpu_draws"] == 9
    assert metrics["gpu_primitive_batches"] == 4
    assert metrics["gpu_image_batches"] == 2
    assert metrics["texture_cache_hits"] == 7
    assert metrics["text_cache_hits"] == 5
    assert metrics["frames_presented"] == 8
    assert metrics["pixel_readbacks"] == 1


def test_canvas_benchmark_stress_variants_are_registered(monkeypatch) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakeGs:
        P2D = "p2d"
        WEBGL = "webgl"
        CENTER = "center"
        CORNER = "corner"

        def __getattr__(self, name: str):
            def recorder(*args: object, **_kwargs: object) -> None:
                calls.append((name, args))

            return recorder

        def frame_count(self) -> int:
            return 1

    fake = FakeGs()
    monkeypatch.setattr("canvas_backend_perf_scenes.gs", fake)
    monkeypatch.setattr("canvas_backend_perf_scenes.sprites", [object()])

    for variant in (
        "stress_primitives_10k",
        "stress_primitives_50k",
        "stress_primitives_100k",
        "stress_sprites_10k",
        "stress_sprites_50k",
        "stress_text_1k",
        "stress_sprite_text_overlay",
    ):
        calls.clear()
        draw_scene(variant)
        assert calls, variant


def test_canvas_benchmark_setup_accepts_stress_variants(monkeypatch) -> None:
    created: list[tuple[object, ...]] = []

    class FakeGs:
        P2D = "p2d"
        WEBGL = "webgl"

        def create_canvas(self, *args: object) -> None:
            created.append(args)

        def frame_rate(self, *_args: object) -> None:
            pass

        def create_image(self, *_args: object):
            class FakeImage:
                width = 0
                height = 0

                def set(self, *_set_args: object) -> None:
                    pass

            return FakeImage()

    fake = FakeGs()
    monkeypatch.setattr("canvas_backend_perf_scenes.gs", fake)

    class FakeSprite:
        def to_rgba_bytes(self) -> bytes:
            return b""

    monkeypatch.setattr("canvas_backend_perf_scenes._sprite", lambda *_args: FakeSprite())
    monkeypatch.setattr("canvas_backend_perf_scenes._reset_asteroids", lambda: None)

    setup_scene("stress_sprites_10k")

    assert created == [(720, 480, "p2d")]
