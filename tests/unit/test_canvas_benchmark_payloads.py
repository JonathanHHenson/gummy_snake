from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmark"
if str(BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_DIR))


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
            "bridge_calls": 11,
            "gpu_draws": 3,
            "pixel_readbacks": 1,
            "native": {
                "bridge_calls": 2,
                "gpu_draws": 9,
                "gpu_primitive_batches": 4,
                "gpu_image_batches": 2,
                "native_draw_commands": 6,
                "native_triangle_commands": 3,
                "native_ellipse_commands": 1,
                "native_image_commands": 2,
                "native_text_commands": 4,
                "native_model_commands": 1,
                "native_erase_commands": 1,
                "native_region_effect_commands": 1,
                "native_primitive_instance_commands": 2,
                "native_staged_primitive_vertices": 18,
                "native_staged_image_vertices": 12,
                "native_primitive_records": 5,
                "native_primitive_batches": 1,
                "native_command_ingest_time_ms": 1.25,
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
    assert metrics["bridge_calls"] == 11
    assert metrics["python_bridge_calls"] == 11
    assert metrics["native_bridge_calls"] == 2
    assert metrics["native_draw_commands"] == 6
    assert metrics["native_triangle_commands"] == 3
    assert metrics["native_ellipse_commands"] == 1
    assert metrics["native_image_commands"] == 2
    assert metrics["native_text_commands"] == 4
    assert metrics["native_model_commands"] == 1
    assert metrics["native_erase_commands"] == 1
    assert metrics["native_region_effect_commands"] == 1
    assert metrics["native_primitive_instance_commands"] == 2
    assert metrics["native_staged_primitive_vertices"] == 18
    assert metrics["native_staged_image_vertices"] == 12
    assert metrics["native_primitive_records"] == 5
    assert metrics["native_primitive_batches"] == 1
    assert metrics["native_command_ingest_time_ms"] == 1.25


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

    class FakeRustImage:
        _rust_image = object()

    class FakeSprite:
        rust_image = FakeRustImage()

    class FakeCanvas:
        def replay_fill_primitive_batch(self) -> bool:
            calls.append(("replay_fill_primitive_batch", ()))
            return False

        def batch_fill_primitives(self, *args: object) -> None:
            calls.append(("batch_fill_primitives", args))

        def batch_canvas_images(self, *args: object) -> None:
            calls.append(("batch_canvas_images", args))

    class FakeRenderer:
        def _matrix_payload(self, matrix: object) -> object:
            return matrix

        def _style_payload(self, style: object) -> object:
            return style

        def _require_canvas(self) -> FakeCanvas:
            return FakeCanvas()

        def _count(self, name: str, amount: int = 1) -> None:
            calls.append((name, (amount,)))

        def _call(self, _operation: str, callback, *args: object):
            return callback(*args)

    class FakeContext:
        renderer = FakeRenderer()

        class state:
            class transform:
                matrix = object()

            style = object()

    monkeypatch.setattr("canvas_backend_perf_scenes.require_context", lambda: FakeContext())
    monkeypatch.setattr("canvas_backend_perf_scenes.sprites", [FakeSprite()])

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
