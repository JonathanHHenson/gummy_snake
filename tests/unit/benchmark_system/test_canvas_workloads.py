from __future__ import annotations

import sys
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest

from benchmarks.suites.canvas import workloads
from benchmarks.suites.canvas.workloads import (
    CanvasWorkloadError,
    ExecutionRouteError,
    build_workload,
    dispatch,
)


@dataclass
class _Context:
    width: int = 16
    height: int = 12
    density: float = 1.0
    frame_count: int = 0
    pixels: bytearray = field(default_factory=bytearray)

    def pixel_density(self) -> float:
        return self.density

    def load_pixel_bytes(self) -> bytes:
        if not self.pixels:
            self.pixels = bytearray(
                round(self.width * self.density) * round(self.height * self.density) * 4
            )
        return bytes(self.pixels)

    def performance_diagnostics(self) -> dict[str, object]:
        return {
            "enabled": True,
            "counters": {"pixel_readback": 1},
            "messages": [],
            "renderer": self.renderer_performance_counters(),
        }

    def renderer_performance_counters(self) -> dict[str, object]:
        return {
            "cpu_fallbacks": 0,
            "frames_presented": self.frame_count,
            "primitive_batch_records": 1,
            "direct_shape_finalizations": 1,
            "image_cache_misses": 1,
            "image_cache_hits": 1,
            "texture_uploads": 1,
            "text_cache_misses": 1,
            "text_cache_hits": 1,
            "pixel_readbacks": 1,
            "pixel_readback_requested_bytes": 1,
            "pixel_readback_copied_bytes": 1,
            "pixel_uploads": 1,
            "gpu_region_effect_passes": 1,
        }

    def frame_pacing_diagnostics(self) -> dict[str, object]:
        return {
            "enabled": True,
            "frames": self.frame_count,
            "event_polls": 0,
            "event_poll_duration_ms_total": 0.0,
            "max_event_poll_duration_ms": 0.0,
            "mean_event_poll_duration_ms": 0.0,
        }

    def set_pixel(self, x: float, y: float, rgba: tuple[int, int, int, int]) -> None:
        width = round(self.width * self.density)
        physical_x = round(x * self.density)
        physical_y = round(y * self.density)
        offset = (physical_y * width + physical_x) * 4
        if 0 <= offset <= len(self.load_pixel_bytes()) - 4:
            self.pixels[offset : offset + 4] = bytes(rgba)


class _SpriteImage:
    """Minimal mutable public-image stand-in for dispatched sprite case tests."""

    def __init__(self) -> None:
        self.pixels: dict[tuple[int, int], tuple[int, int, int, int]] = {
            (0, 0): (255, 204, 0, 255),
            (1, 0): (255, 204, 0, 255),
        }
        self.mutations: list[tuple[int, int, tuple[int, int, int, int]]] = []

    def set(self, x: int, y: int, color: tuple[int, int, int, int]) -> None:
        self.pixels[x, y] = color
        self.mutations.append((x, y, color))


class _PublicLifecycleApi:
    """Small public-API lifecycle model used to assert dispatched callback intent."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.context = _Context()
        self.looping = True
        self.redraw_requested = False
        self.fill_color = (255, 255, 255, 255)
        self.shape_vertices: list[tuple[float, float]] = []

    def enable_performance_diagnostics(self, enabled: bool, *, reset: bool) -> None:
        assert enabled is True
        assert reset is True
        self.calls.append("enable_performance_diagnostics")

    def enable_frame_pacing_diagnostics(self, enabled: bool, *, reset: bool) -> None:
        assert enabled is True
        assert reset is True
        self.calls.append("enable_frame_pacing_diagnostics")

    def create_canvas(self, width: int, height: int, *, pixel_density: float) -> None:
        self.calls.append("create_canvas")
        self.context.width = width
        self.context.height = height
        self.context.density = pixel_density
        self.context.pixels = bytearray(
            round(width * pixel_density) * round(height * pixel_density) * 4
        )

    def frame_rate(self, value: float) -> None:
        del value
        self.calls.append("frame_rate")

    def frame_count(self) -> int:
        return self.context.frame_count

    def resize_canvas(self, width: int, height: int, *, pixel_density: float) -> None:
        self.calls.append("resize_canvas")
        self.create_canvas(width, height, pixel_density=pixel_density)

    def background(self, *values: int) -> None:
        self.calls.append("background")
        if len(values) == 1:
            rgba = (values[0], values[0], values[0], 255)
        elif len(values) == 3:
            rgba = (*values, 255)
        else:
            rgba = values
        self.context.pixels[:] = bytes(rgba) * (self.context.width * self.context.height)

    def loop(self) -> None:
        self.calls.append("loop")
        self.looping = True

    def no_loop(self) -> None:
        self.calls.append("no_loop")
        self.looping = False

    def redraw(self) -> None:
        self.calls.append("redraw")
        self.redraw_requested = True

    def fill(self, red: int, green: int, blue: int, alpha: int = 255) -> None:
        self.calls.append("fill")
        self.fill_color = (red, green, blue, alpha)

    def stroke(self, *values: int) -> None:
        del values
        self.calls.append("stroke")

    def no_stroke(self) -> None:
        self.calls.append("no_stroke")

    def no_smooth(self) -> None:
        self.calls.append("no_smooth")

    def stroke_weight(self, value: float) -> None:
        del value
        self.calls.append("stroke_weight")

    def push(self) -> None:
        self.calls.append("push")

    def pop(self) -> None:
        self.calls.append("pop")

    def translate(self, x: float, y: float) -> None:
        del x, y
        self.calls.append("translate")

    def rotate(self, angle: float) -> None:
        del angle
        self.calls.append("rotate")

    def shear_x(self, angle: float) -> None:
        del angle
        self.calls.append("shear_x")

    def rect(self, x: float, y: float, width: float, height: float) -> None:
        del width, height
        self.calls.append("rect")
        self.context.set_pixel(x, y, self.fill_color)

    def image(self, image: _SpriteImage, x: float, y: float, *source: float) -> None:
        self.calls.append("image")
        if len(source) == 6:
            source_x, source_y = int(source[2]), int(source[3])
            self.context.set_pixel(x, y, image.pixels[source_x, source_y])

    def text_size(self, value: float) -> None:
        del value
        self.calls.append("text_size")

    def text(self, value: str, x: float, y: float) -> None:
        del value, x, y
        self.calls.append("text")

    def set(self, x: int, y: int, rgba: tuple[int, int, int, int]) -> None:
        self.calls.append("set")
        self.context.set_pixel(x, y, rgba)

    def load_pixels(self) -> bytearray:
        self.calls.append("load_pixels")
        self.context.load_pixel_bytes()
        return self.context.pixels

    def update_pixels(self, pixels: bytearray) -> None:
        assert pixels is self.context.pixels
        self.calls.append("update_pixels")

    def filter(self, mode: str) -> None:
        assert mode == self.INVERT
        self.calls.append("filter")
        for offset in range(0, len(self.context.pixels), 4):
            self.context.pixels[offset] = 255 - self.context.pixels[offset]
            self.context.pixels[offset + 1] = 255 - self.context.pixels[offset + 1]
            self.context.pixels[offset + 2] = 255 - self.context.pixels[offset + 2]

    def circle(self, x: float, y: float, diameter: float) -> None:
        del x, y, diameter
        self.calls.append("circle")

    def triangle(self, *coordinates: float) -> None:
        del coordinates
        self.calls.append("triangle")

    def begin_shape(self) -> None:
        self.calls.append("begin_shape")
        self.shape_vertices = []

    def vertex(self, x: float, y: float) -> None:
        self.calls.append("vertex")
        self.shape_vertices.append((x, y))

    def end_shape(self, mode: object) -> None:
        del mode
        self.calls.append("end_shape")
        if self.fill_color == (17, 43, 97, 255):
            self.context.set_pixel(2, 2, self.fill_color)

    @contextmanager
    def clip_path(self):
        self.calls.append("clip_path")
        yield

    def end_clip(self) -> None:
        self.calls.append("end_clip")

    @property
    def CLOSE(self) -> str:
        return "close"

    @property
    def INVERT(self) -> str:
        return "invert"

    def fast(self) -> _PublicLifecycleApi:
        self.calls.append("fast")
        return self

    def run(
        self,
        *,
        setup: Callable[[], None],
        draw: Callable[[], None],
        headless: bool,
        max_frames: int,
    ) -> _Context:
        self.calls.append("run-headless" if headless else "run-native")
        setup()
        for _ in range(max_frames):
            if self.looping or self.redraw_requested:
                draw()
                self.context.frame_count += 1
                # Sketch._draw_frame clears this after an accepted redraw frame.
                self.redraw_requested = False
            elif not headless:
                # The bounded interactive route exits after observing its idle tick.
                break
        return self.context


def test_canvas_workload_builder_preserves_distinct_headless_and_native_routes() -> None:
    parameters = {
        "frames": 1,
        "width": 16,
        "height": 12,
        "density": 1.0,
        "draw_count": 4,
        "case_kind": "uniform-primitives",
        "primitive_kind": "rect",
        "mutation_mode": "static",
        "dispatch_route": "fast",
        "required_counters": ["primitive_batch_records", "frames_presented"],
    }

    headless = build_workload("primitives-paths-order", parameters, "headless")
    native = build_workload("primitives-paths-order", parameters, "native-interactive")

    assert headless.headless is True
    assert native.headless is False
    assert native.execution_class.value == "native-interactive"
    with pytest.raises(ExecutionRouteError, match="require execution_class"):
        build_workload("lifecycle-hidpi", {}, "simulated-realtime")
    with pytest.raises(CanvasWorkloadError, match="dispatch_route"):
        build_workload("lifecycle-hidpi", {"dispatch_route": "renderer-adapter"}, "headless")


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({}, "case_kind"),
        (
            {
                "case_kind": "uniform-primitives",
                "draw_count": 1,
                "primitive_kind": "line",
                "mutation_mode": "static",
            },
            "primitive_kind",
        ),
        (
            {
                "case_kind": "mixed-primitives",
                "draw_count": 1,
                "style_count": 16,
                "mutation_mode": "static",
                "dispatch_route": "fast",
            },
            "fast dispatch",
        ),
        (
            {
                "case_kind": "paths",
                "draw_count": 1,
                "segments_per_path": 2,
                "unused_scale": 4,
            },
            "unexecuted or unsupported",
        ),
        (
            {
                "case_kind": "nested-clips",
                "draw_count": 1,
                "clip_depth": 1,
                "clip_segments": 3,
            },
            "at least 2",
        ),
    ],
)
def test_primitive_path_builder_rejects_missing_invalid_and_unexecuted_parameters(
    parameters: dict[str, object], message: str
) -> None:
    with pytest.raises(CanvasWorkloadError, match=message):
        build_workload("primitives-paths-order", parameters, "headless")


def test_native_canvas_workload_requires_presentation_counter() -> None:
    with pytest.raises(CanvasWorkloadError, match="frames_presented"):
        build_workload(
            "primitives-paths-order",
            {
                "case_kind": "uniform-primitives",
                "draw_count": 1,
                "primitive_kind": "rect",
                "mutation_mode": "static",
                "required_counters": ["primitive_batch_records"],
            },
            "native-interactive",
        )


@pytest.mark.parametrize(
    ("case_kind", "parameters", "required_calls"),
    [
        (
            "uniform-primitives",
            {"primitive_kind": "rect", "mutation_mode": "static"},
            {"rect"},
        ),
        (
            "mixed-primitives",
            {"style_count": 16, "mutation_mode": "static"},
            {"stroke", "shear_x", "triangle"},
        ),
        ("paths", {"segments_per_path": 4}, {"begin_shape", "vertex", "end_shape"}),
        ("nested-clips", {"clip_depth": 2, "clip_segments": 4}, {"clip_path", "end_clip"}),
    ],
)
def test_primitive_path_cases_execute_declared_public_work_and_order_sentinels(
    monkeypatch: pytest.MonkeyPatch,
    case_kind: str,
    parameters: dict[str, object],
    required_calls: set[str],
) -> None:
    api = _PublicLifecycleApi()
    monkeypatch.setitem(sys.modules, "gummysnake", api)
    run = dispatch(
        "primitives-paths-order",
        {
            "frames": 1,
            "width": 32,
            "height": 24,
            "density": 1.0,
            "draw_count": 4,
            "case_kind": case_kind,
            "required_counters": [
                "primitive_batch_records"
                if case_kind in {"uniform-primitives", "mixed-primitives"}
                else "direct_shape_finalizations"
            ],
            **parameters,
        },
        "headless",
    )

    assert run.draw_records == 4
    assert run.draw_callbacks == 1
    assert required_calls <= set(api.calls)


@pytest.mark.parametrize(
    ("mode", "frames", "expected_draws", "lifecycle_calls"),
    [
        ("continuous-clear-loop", 3, 3, ["loop"]),
        ("explicit-redraw", 2, 1, ["no_loop", "redraw"]),
        ("no-loop-idle", 2, 1, ["no_loop"]),
    ],
)
@pytest.mark.parametrize("execution_class", ["headless", "native-interactive"])
def test_lifecycle_modes_dispatch_distinct_public_calls_and_exact_accounting(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    frames: int,
    expected_draws: int,
    lifecycle_calls: list[str],
    execution_class: str,
) -> None:
    api = _PublicLifecycleApi()
    monkeypatch.setitem(sys.modules, "gummysnake", api)

    run = dispatch(
        "lifecycle-hidpi",
        {
            "frames": frames,
            "expected_draw_callbacks": expected_draws,
            "lifecycle_mode": mode,
            "width": 16,
            "height": 12,
            "density": 1.0,
            "required_counters": ["frames_presented"],
        },
        execution_class,
    )

    assert run.setup_callbacks == 1
    assert run.draw_callbacks == expected_draws
    assert run.frame_count == expected_draws
    assert run.physical_desktop_requested is (execution_class == "native-interactive")
    assert [call for call in api.calls if call in {"loop", "no_loop", "redraw"}] == lifecycle_calls
    assert api.calls[0] == ("run-headless" if run.plan.headless else "run-native")


@pytest.mark.parametrize(
    ("case_kind", "parameters", "draw_count", "required_calls"),
    [
        (
            "sprite-uniqueness-mutation",
            {"sprite_count": 2, "mutation_count": 1},
            3,
            {"image", "no_smooth"},
        ),
        ("text-reuse-script", {"text_reuse_count": 2}, 6, {"text", "text_size", "set"}),
        (
            "pixel-read-write-locality",
            {"locality_width": 2, "locality_height": 2},
            4,
            {"load_pixels", "update_pixels"},
        ),
        ("ordered-effects", {"effect": "invert"}, 1, {"filter", "set"}),
    ],
)
def test_feature_cases_dispatch_real_public_work_with_exact_accounting(
    monkeypatch: pytest.MonkeyPatch,
    case_kind: str,
    parameters: dict[str, object],
    draw_count: int,
    required_calls: set[str],
) -> None:
    api = _PublicLifecycleApi()
    sprites: list[_SpriteImage] = []
    monkeypatch.setitem(sys.modules, "gummysnake", api)
    monkeypatch.setattr(
        workloads, "sprite_image", lambda: sprites.append(_SpriteImage()) or sprites[-1]
    )

    run = dispatch(
        "images-text-pixels-effects",
        {
            "frames": 1,
            "width": 32,
            "height": 24,
            "density": 1.0,
            "draw_count": draw_count,
            "case_kind": case_kind,
            "required_counters": ["pixel_readbacks"],
            **parameters,
        },
        "headless",
    )

    assert run.draw_records == draw_count
    assert required_calls <= set(api.calls)
    if case_kind == "sprite-uniqueness-mutation":
        assert len(sprites) == 2
        assert sprites[0].mutations[0] == (1, 0, (17, 43, 97, 255))


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        (
            {
                "case_kind": "sprite-uniqueness-mutation",
                "sprite_count": 2,
                "mutation_count": 1,
                "draw_count": 2,
            },
            "draw_count",
        ),
        (
            {"case_kind": "text-reuse-script", "text_reuse_count": 1, "draw_count": 1},
            "draw_count",
        ),
        (
            {
                "case_kind": "pixel-read-write-locality",
                "locality_width": 2,
                "locality_height": 2,
                "draw_count": 3,
            },
            "draw_count",
        ),
        ({"case_kind": "ordered-effects", "effect": "gray", "draw_count": 1}, "invert"),
        (
            {
                "case_kind": "ordered-effects",
                "effect": "invert",
                "draw_count": 1,
                "unused_matrix": 2,
            },
            "unexecuted or unsupported",
        ),
    ],
)
def test_feature_builder_rejects_invalid_or_dormant_parameters(
    parameters: dict[str, object], message: str
) -> None:
    with pytest.raises(CanvasWorkloadError, match=message):
        build_workload("images-text-pixels-effects", parameters, "headless")


def test_lifecycle_dynamic_rate_and_resize_sequences_are_exact_runtime_parameters() -> None:
    rates = build_workload(
        "lifecycle-hidpi",
        {
            "frames": 4,
            "expected_draw_callbacks": 4,
            "lifecycle_mode": "dynamic-frame-rate",
            "frame_rate_sequence": [30, 60, 120, 30],
        },
        "headless",
    )
    resize = build_workload(
        "lifecycle-hidpi",
        {
            "frames": 2,
            "expected_draw_callbacks": 2,
            "lifecycle_mode": "resize-density-churn",
            "resize_sequence": [
                {"width": 32, "height": 24, "density": 2.0},
                {"width": 16, "height": 12, "density": 1.5},
            ],
        },
        "headless",
    )

    assert rates.expected_draw_callbacks == 4
    assert (resize.final_width, resize.final_height, resize.final_density) == (16, 12, 1.5)


@pytest.mark.parametrize(
    ("workload_id", "parameters", "expected_records"),
    [
        (
            "primitives-paths-order",
            {
                "case_kind": "polyline",
                "draw_count": 50_000,
                "segment_count": 50_000,
                "required_counters": ["direct_shape_finalizations"],
            },
            50_000,
        ),
        (
            "images-text-pixels-effects",
            {
                "case_kind": "effect-matrix",
                "draw_count": 8,
                "effect_family": "blend",
                "effect_name": "multiply",
                "operation_count": 8,
                "required_counters": [],
            },
            8,
        ),
        (
            "assets-media-models",
            {
                "case_kind": "media-frame-conversion",
                "conversion_count": 300,
                "conversion_width": 3840,
                "conversion_height": 2160,
                "channels": 4,
                "required_counters": [],
            },
            300,
        ),
    ],
)
def test_full_scale_case_identities_validate_without_downscaling(
    workload_id: str, parameters: dict[str, object], expected_records: int
) -> None:
    plan = build_workload(workload_id, parameters, "headless")

    assert plan.expected_draw_records == expected_records
    assert plan.parameters == parameters


def test_lifecycle_mode_builder_rejects_ambiguous_work_accounting() -> None:
    with pytest.raises(CanvasWorkloadError, match="expected_draw_callbacks to equal frames"):
        build_workload(
            "lifecycle-hidpi",
            {"frames": 2, "lifecycle_mode": "continuous-clear-loop", "expected_draw_callbacks": 1},
            "headless",
        )
    with pytest.raises(CanvasWorkloadError, match="at least two bounded scheduling ticks"):
        build_workload(
            "lifecycle-hidpi",
            {"frames": 1, "lifecycle_mode": "explicit-redraw"},
            "headless",
        )
    with pytest.raises(CanvasWorkloadError, match="exactly one draw callback"):
        build_workload(
            "lifecycle-hidpi",
            {"frames": 2, "lifecycle_mode": "no-loop-idle", "expected_draw_callbacks": 2},
            "headless",
        )
    with pytest.raises(CanvasWorkloadError, match="lifecycle_mode"):
        build_workload("lifecycle-hidpi", {"lifecycle_mode": "implicit-retry"}, "headless")
