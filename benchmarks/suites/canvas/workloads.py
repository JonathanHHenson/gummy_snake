"""Static Canvas workload plans and their bounded production-path dispatcher.

``dispatch(workload_id, parameters, execution_class)`` is the intended worker
integration point. It constructs real Gummy Snake callbacks and runs them through
``gs.run`` (or the public ``Sketch`` facade for object mode).  It intentionally
does not time, emulate, or substitute a renderer route; the benchmark worker owns
timing around this bounded work.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import cos, sin, tau
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol, cast

from benchmarks.governance import ExecutionClass

from .diagnostics import DiagnosticsSnapshot, capture_canvas_diagnostics
from .fixtures import (
    MEDIA_FRAME_BGR,
    MEDIA_FRAME_BGRA,
    MEDIA_FRAME_GRAY,
    PIXEL_BUFFER,
    TEXT_CORPUS,
    MediaFrameFixture,
    generated_media_frame,
    generated_rgba_fixture,
    sprite_image,
    validate_manifest,
)
from .oracles import (
    PixelSentinel,
    assert_canvas_state,
    assert_hidpi_dimensions,
    assert_media_frame_rgba,
    assert_ordered_layers,
    assert_png_export,
    assert_presented_frames,
)


class CanvasWorkloadError(ValueError):
    """A static Canvas workload declaration cannot be constructed safely."""


class ExecutionRouteError(CanvasWorkloadError):
    """A request would use an unsupported or silently substituted execution route."""


class MutableSpriteImage(Protocol):
    """Public mutable-image operations required by sprite mutation cases."""

    def set(self, x: int, y: int, value: tuple[int, int, int, int]) -> None: ...

    def update_pixels(self, pixels: bytes | bytearray) -> None: ...


class CompletedCanvasContext(Protocol):
    """Public post-run context operations consumed by the dispatcher."""

    width: int
    height: int
    frame_count: int

    def pixel_density(self) -> float: ...

    def load_pixel_bytes(self) -> bytes: ...

    def performance_diagnostics(self) -> dict[str, object]: ...

    def renderer_performance_counters(self) -> dict[str, object]: ...

    def frame_pacing_diagnostics(self) -> dict[str, object]: ...


@dataclass(slots=True)
class _CallbackAccounting:
    """Actual lifecycle callbacks and declared visual records from one run."""

    setup_calls: int = 0
    draw_calls: int = 0
    draw_records: int = 0


@dataclass(frozen=True, slots=True)
class WorkloadPlan:
    """Validated bounded work to execute through public Gummy Snake APIs."""

    workload_id: str
    execution_class: ExecutionClass
    headless: bool
    frames: int
    width: int
    height: int
    density: float
    final_width: int
    final_height: int
    final_density: float
    dispatch_route: str
    lifecycle_mode: str | None
    expected_draw_callbacks: int
    expected_draw_records: int
    parameters: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class WorkloadRun:
    """Observable result of one real bounded workload execution."""

    plan: WorkloadPlan
    frame_count: int
    pixels: bytes
    diagnostics: DiagnosticsSnapshot
    setup_callbacks: int
    draw_callbacks: int
    draw_records: int
    physical_desktop_requested: bool


_WORKLOAD_IDS = frozenset(
    {
        "lifecycle-hidpi",
        "primitives-paths-order",
        "images-text-pixels-effects",
        "assets-media-models",
    }
)
_PUBLIC_DISPATCH_ROUTES = frozenset({"global", "object", "fast"})
_LIFECYCLE_MODES = frozenset(
    {
        "empty-loop",
        "continuous-clear-loop",
        "explicit-redraw",
        "no-loop-idle",
        "dynamic-frame-rate",
        "resize-density-churn",
    }
)
_PRIMITIVE_CASE_KINDS = frozenset(
    {
        "uniform-primitives",
        "mixed-primitives",
        "independent-lines",
        "polyline",
        "paths",
        "curves-contours",
        "nested-clips",
        "ordered-family-stream",
    }
)
_MEDIA_CASE_KINDS = frozenset(
    {
        "media-frame-conversion",
        "image-asset-operations",
        "png-export-roundtrip",
        "offscreen-resource-churn",
        "storage-compute-lifecycle",
        "model-import-export",
    }
)
_MEDIA_FRAME_FIXTURES: tuple[MediaFrameFixture, ...] = (
    MEDIA_FRAME_GRAY,
    MEDIA_FRAME_BGR,
    MEDIA_FRAME_BGRA,
)

_FEATURE_CASE_KINDS = frozenset(
    {
        "sprite-uniqueness-mutation",
        "text-reuse-script",
        "pixel-read-write-locality",
        "ordered-effects",
        "sprite-matrix",
        "text-matrix",
        "pixel-readback-matrix",
        "pixel-write-matrix",
        "effect-matrix",
    }
)
_SENTINEL_WORK = (17, 43, 97, 255)
_SENTINEL_RESTORED = (229, 157, 43, 255)
_SPRITE_SENTINEL = (17, 43, 97, 255)
_TEXT_SENTINEL = (229, 157, 43, 255)
_EFFECT_BACKGROUND = (10, 20, 30, 255)
_EFFECT_OVERLAY = (17, 43, 97, 255)
_PIXEL_LOCALITY_ORIGIN = (2, 2)
_FILTER_NAMES = frozenset({"threshold", "gray", "invert", "blur", "posterize", "erode", "dilate"})
_BLEND_NAMES = frozenset(
    {
        "blend",
        "add",
        "darkest",
        "lightest",
        "difference",
        "exclusion",
        "multiply",
        "screen",
        "replace",
    }
)


def _execution_class(value: ExecutionClass | str) -> ExecutionClass:
    try:
        return ExecutionClass(value)
    except ValueError as error:
        raise ExecutionRouteError(f"unknown Canvas execution class: {value!r}") from error


def _positive_int(parameters: Mapping[str, object], name: str, default: int, maximum: int) -> int:
    value = parameters.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise CanvasWorkloadError(f"{name} must be an integer in [1, {maximum}]")
    return value


def _positive_float(
    parameters: Mapping[str, object], name: str, default: float, maximum: float
) -> float:
    value = parameters.get(name, default)
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise CanvasWorkloadError(f"{name} must be a positive number")
    try:
        result = float(value)
    except ValueError as error:
        raise CanvasWorkloadError(f"{name} must be a positive number") from error
    if not 0 < result <= maximum:
        raise CanvasWorkloadError(f"{name} must be in (0, {maximum}]")
    return result


def _number_sequence(
    parameters: Mapping[str, object], name: str, *, length: int, maximum: float
) -> tuple[float, ...]:
    raw = parameters.get(name)
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise CanvasWorkloadError(f"{name} must be a sequence")
    if len(raw) != length:
        raise CanvasWorkloadError(f"{name} must contain exactly {length} values")
    values: list[float] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, str | int | float):
            raise CanvasWorkloadError(f"{name} values must be positive numbers")
        converted = float(value)
        if not 0 < converted <= maximum:
            raise CanvasWorkloadError(f"{name} values must be in (0, {maximum}]")
        values.append(converted)
    return tuple(values)


def _resize_sequence(
    parameters: Mapping[str, object], frames: int
) -> tuple[tuple[int, int, float], ...]:
    raw = parameters.get("resize_sequence")
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes) or len(raw) != frames:
        raise CanvasWorkloadError("resize_sequence must contain one transition per frame")
    transitions: list[tuple[int, int, float]] = []
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise CanvasWorkloadError(f"resize_sequence[{index}] must be a mapping")
        if set(value) != {"width", "height", "density"}:
            raise CanvasWorkloadError(
                f"resize_sequence[{index}] requires exactly width, height, and density"
            )
        width = _positive_int(value, "width", 1, 3_840)
        height = _positive_int(value, "height", 1, 2_160)
        density = _positive_float(value, "density", 1.0, 4.0)
        transitions.append((width, height, density))
    return tuple(transitions)


def _lifecycle_accounting(
    workload_id: str, parameters: Mapping[str, object], frames: int
) -> tuple[str | None, int]:
    """Validate the intentionally distinct Canvas lifecycle modes and their work."""

    if workload_id != "lifecycle-hidpi":
        return None, frames
    mode = str(parameters.get("lifecycle_mode", "continuous-clear-loop"))
    if mode not in _LIFECYCLE_MODES:
        allowed = sorted(_LIFECYCLE_MODES)
        raise CanvasWorkloadError(f"lifecycle_mode must be one of {allowed}, got {mode!r}")
    continuous = {
        "empty-loop",
        "continuous-clear-loop",
        "dynamic-frame-rate",
        "resize-density-churn",
    }
    default_draws = frames if mode in continuous else 1
    expected_draws = _positive_int(parameters, "expected_draw_callbacks", default_draws, frames)
    if mode in continuous and expected_draws != frames:
        raise CanvasWorkloadError(f"{mode} requires expected_draw_callbacks to equal frames")
    if mode not in continuous:
        if frames < 2:
            raise CanvasWorkloadError(f"{mode} requires at least two bounded scheduling ticks")
        if expected_draws != 1:
            raise CanvasWorkloadError(f"{mode} requires exactly one draw callback")
    if mode == "dynamic-frame-rate":
        _number_sequence(parameters, "frame_rate_sequence", length=frames, maximum=1_000.0)
    elif "frame_rate_sequence" in parameters:
        raise CanvasWorkloadError("frame_rate_sequence requires dynamic-frame-rate mode")
    if mode == "resize-density-churn":
        _resize_sequence(parameters, frames)
    elif "resize_sequence" in parameters:
        raise CanvasWorkloadError("resize_sequence requires resize-density-churn mode")
    allowed = {
        "frames",
        "expected_draw_callbacks",
        "lifecycle_mode",
        "width",
        "height",
        "density",
        "frame_rate",
        "dispatch_route",
        "required_counters",
        "frame_rate_sequence",
        "resize_sequence",
    }
    unexpected = sorted(set(parameters) - allowed)
    if unexpected:
        raise CanvasWorkloadError(
            "lifecycle case has unexecuted or unsupported parameter(s): " + ", ".join(unexpected)
        )
    return mode, expected_draws


def _required_primitive_parameters(parameters: Mapping[str, object]) -> int:
    """Validate that every primitive/path catalog value is executed by its case."""

    kind = parameters.get("case_kind")
    if not isinstance(kind, str) or kind not in _PRIMITIVE_CASE_KINDS:
        allowed = sorted(_PRIMITIVE_CASE_KINDS)
        raise CanvasWorkloadError(f"case_kind must be one of {allowed}, got {kind!r}")
    if "draw_count" not in parameters:
        raise CanvasWorkloadError("primitive/path cases require a declared draw_count")
    draw_count = _positive_int(parameters, "draw_count", 1, 100_000)
    common = {
        "case_kind",
        "draw_count",
        "frames",
        "width",
        "height",
        "density",
        "frame_rate",
        "dispatch_route",
        "required_counters",
    }
    case_parameters = {
        "uniform-primitives": {"primitive_kind", "mutation_mode"},
        "mixed-primitives": {"style_count", "mutation_mode"},
        "independent-lines": {"segment_count"},
        "polyline": {"segment_count"},
        "paths": {"segments_per_path"},
        "curves-contours": {"curve_kind", "segment_count"},
        "nested-clips": {"clip_depth", "clip_segments"},
        "ordered-family-stream": {"switch_count"},
    }
    allowed_parameters = common | case_parameters[kind]
    unexpected = sorted(set(parameters) - allowed_parameters)
    if unexpected:
        raise CanvasWorkloadError(
            f"{kind} has unexecuted or unsupported parameter(s): {', '.join(unexpected)}"
        )
    missing = sorted(case_parameters[kind] - set(parameters))
    if missing:
        raise CanvasWorkloadError(f"{kind} requires parameter(s): {', '.join(missing)}")
    if parameters.get("dispatch_route", "global") == "fast" and kind != "uniform-primitives":
        raise CanvasWorkloadError("fast dispatch is currently supported only by uniform-primitives")
    if kind == "uniform-primitives":
        primitive_kind = parameters["primitive_kind"]
        if primitive_kind not in {"rect", "circle", "triangle"}:
            raise CanvasWorkloadError("primitive_kind must be 'rect', 'circle', or 'triangle'")
        if parameters["mutation_mode"] not in {"static", "low-mutation", "dynamic"}:
            raise CanvasWorkloadError("mutation_mode must be static, low-mutation, or dynamic")
    elif kind == "mixed-primitives":
        _positive_int(parameters, "style_count", 16, 256)
        if parameters["mutation_mode"] not in {"static", "low-mutation", "dynamic"}:
            raise CanvasWorkloadError("mutation_mode must be static, low-mutation, or dynamic")
    elif kind in {"independent-lines", "polyline"}:
        segments = _positive_int(parameters, "segment_count", 1, 50_000)
        if draw_count != segments:
            raise CanvasWorkloadError(f"{kind} draw_count must equal segment_count")
    elif kind == "paths":
        _positive_int(parameters, "segments_per_path", 2, 4_096)
    elif kind == "curves-contours":
        if parameters["curve_kind"] not in {"quadratic", "cubic", "arc", "contour-hole"}:
            raise CanvasWorkloadError("unsupported curve_kind")
        segments = _positive_int(parameters, "segment_count", 1, 4_096)
        if draw_count != segments:
            raise CanvasWorkloadError("curves-contours draw_count must equal segment_count")
    elif kind == "nested-clips":
        if draw_count < 2:
            raise CanvasWorkloadError("nested-clips requires draw_count of at least 2")
        _positive_int(parameters, "clip_depth", 1, 16)
        _positive_int(parameters, "clip_segments", 3, 4_096)
    else:
        switches = _positive_int(parameters, "switch_count", 1, 10_000)
        if draw_count != switches * 4:
            raise CanvasWorkloadError(
                "ordered-family-stream draw_count must equal switch_count * 4"
            )
    if not _required_counters(parameters):
        raise CanvasWorkloadError("primitive/path cases require declared required_counters")
    return draw_count


def _required_feature_parameters(parameters: Mapping[str, object]) -> int:
    """Validate that every image/text/pixel/effect case has concrete executed work."""

    kind = parameters.get("case_kind")
    if not isinstance(kind, str) or kind not in _FEATURE_CASE_KINDS:
        allowed = sorted(_FEATURE_CASE_KINDS)
        raise CanvasWorkloadError(f"case_kind must be one of {allowed}, got {kind!r}")
    if "draw_count" not in parameters:
        raise CanvasWorkloadError("image/text/pixel/effect cases require a declared draw_count")
    draw_count = _positive_int(parameters, "draw_count", 1, 8_294_400)
    common = {
        "case_kind",
        "draw_count",
        "frames",
        "width",
        "height",
        "density",
        "frame_rate",
        "dispatch_route",
        "required_counters",
    }
    case_parameters = {
        "sprite-uniqueness-mutation": {"sprite_count", "mutation_count"},
        "text-reuse-script": {"text_reuse_count"},
        "pixel-read-write-locality": {"locality_width", "locality_height"},
        "ordered-effects": {"effect"},
        "sprite-matrix": {
            "unique_images",
            "source_width",
            "source_height",
            "mutation_mode",
            "sampling",
            "transformed",
            "tinted",
        },
        "text-matrix": {"label_count", "text_mode", "text_size", "transformed", "clipped"},
        "pixel-readback-matrix": {"read_kind", "region_width", "region_height"},
        "pixel-write-matrix": {"write_kind", "region_width", "region_height"},
        "effect-matrix": {"effect_family", "effect_name", "operation_count"},
    }
    unexpected = sorted(set(parameters) - common - case_parameters[kind])
    if unexpected:
        raise CanvasWorkloadError(
            f"{kind} has unexecuted or unsupported parameter(s): {', '.join(unexpected)}"
        )
    missing = sorted(case_parameters[kind] - set(parameters))
    if missing:
        raise CanvasWorkloadError(f"{kind} requires parameter(s): {', '.join(missing)}")
    if parameters.get("dispatch_route", "global") == "fast":
        raise CanvasWorkloadError("fast dispatch is not supported by image/text/pixel/effect cases")
    if kind == "sprite-uniqueness-mutation":
        sprite_count = _positive_int(parameters, "sprite_count", 1, 1_024)
        mutation_count = _positive_int(parameters, "mutation_count", 1, sprite_count)
        if draw_count != sprite_count + 1:
            raise CanvasWorkloadError(
                "sprite-uniqueness-mutation requires draw_count to equal sprite_count + 1"
            )
        if mutation_count > sprite_count:
            raise CanvasWorkloadError("mutation_count cannot exceed sprite_count")
    elif kind == "text-reuse-script":
        reused = _positive_int(parameters, "text_reuse_count", 1, 100_000)
        script_count = 4
        if draw_count != reused + script_count:
            raise CanvasWorkloadError(
                "text-reuse-script requires draw_count to equal text_reuse_count + 4"
            )
    elif kind == "pixel-read-write-locality":
        locality_width = _positive_int(parameters, "locality_width", 1, 256)
        locality_height = _positive_int(parameters, "locality_height", 1, 256)
        if draw_count != locality_width * locality_height:
            raise CanvasWorkloadError(
                "pixel-read-write-locality draw_count must equal the locality rectangle area"
            )
    elif kind == "ordered-effects":
        if parameters["effect"] != "invert":
            raise CanvasWorkloadError("ordered-effects requires effect='invert'")
        if draw_count != 1:
            raise CanvasWorkloadError(
                "ordered-effects requires draw_count to equal one effect pass"
            )
    elif kind == "sprite-matrix":
        unique = _positive_int(parameters, "unique_images", 1, 128)
        _positive_int(parameters, "source_width", 1, 1_920)
        _positive_int(parameters, "source_height", 1, 1_080)
        if parameters["mutation_mode"] not in {"unchanged", "one-pixel", "one-percent", "full"}:
            raise CanvasWorkloadError("unsupported sprite mutation_mode")
        if parameters["sampling"] not in {"linear", "nearest"}:
            raise CanvasWorkloadError("sampling must be linear or nearest")
        if not isinstance(parameters["transformed"], bool) or not isinstance(
            parameters["tinted"], bool
        ):
            raise CanvasWorkloadError("sprite transformed and tinted parameters must be booleans")
        if draw_count < unique:
            raise CanvasWorkloadError("sprite-matrix draw_count cannot be less than unique_images")
    elif kind == "text-matrix":
        labels = _positive_int(parameters, "label_count", 1, 10_000)
        if draw_count != labels:
            raise CanvasWorkloadError("text-matrix draw_count must equal label_count")
        if parameters["text_mode"] not in {"repeated", "unique", "multiscript"}:
            raise CanvasWorkloadError("unsupported text_mode")
        _positive_float(parameters, "text_size", 12.0, 512.0)
        if not isinstance(parameters["transformed"], bool) or not isinstance(
            parameters["clipped"], bool
        ):
            raise CanvasWorkloadError("text transformed and clipped parameters must be booleans")
    elif kind in {"pixel-readback-matrix", "pixel-write-matrix"}:
        width = _positive_int(parameters, "region_width", 1, 3_840)
        height = _positive_int(parameters, "region_height", 1, 2_160)
        if draw_count != width * height:
            raise CanvasWorkloadError(f"{kind} draw_count must equal the declared region area")
        mode_name = "read_kind" if kind == "pixel-readback-matrix" else "write_kind"
        allowed_modes = (
            {"pixel", "region", "full", "pixel-bytes"}
            if kind == "pixel-readback-matrix"
            else {"one-byte", "one-pixel", "row", "block", "full", "overwrite", "composite"}
        )
        if parameters[mode_name] not in allowed_modes:
            raise CanvasWorkloadError(f"unsupported {mode_name}")
    else:
        count = _positive_int(parameters, "operation_count", 1, 10_000)
        if draw_count != count:
            raise CanvasWorkloadError("effect-matrix draw_count must equal operation_count")
        family = parameters["effect_family"]
        name = parameters["effect_name"]
        if family == "filter" and name not in _FILTER_NAMES:
            raise CanvasWorkloadError("unsupported filter effect_name")
        if family == "blend" and name not in _BLEND_NAMES:
            raise CanvasWorkloadError("unsupported blend effect_name")
        if family == "erase" and name != "erase":
            raise CanvasWorkloadError("erase effect family requires effect_name='erase'")
        if family not in {"filter", "blend", "erase"}:
            raise CanvasWorkloadError("unsupported effect_family")
    if not _required_counters(parameters) and not (
        kind == "effect-matrix" and parameters["effect_family"] in {"blend", "erase"}
    ):
        raise CanvasWorkloadError(
            "image/text/pixel/effect cases require declared required_counters"
        )
    return draw_count


def _required_media_parameters(parameters: Mapping[str, object]) -> int:
    """Validate generated asset, media, model, and resource workloads."""

    kind = parameters.get("case_kind")
    if not isinstance(kind, str) or kind not in _MEDIA_CASE_KINDS:
        raise CanvasWorkloadError(
            f"case_kind must be one of {sorted(_MEDIA_CASE_KINDS)}, got {kind!r}"
        )
    common = {
        "case_kind",
        "frames",
        "width",
        "height",
        "density",
        "frame_rate",
        "dispatch_route",
        "required_counters",
    }
    case_parameters = {
        "media-frame-conversion": {
            "conversion_count",
            "conversion_width",
            "conversion_height",
            "channels",
        },
        "image-asset-operations": {"asset_width", "asset_height", "operation_count"},
        "png-export-roundtrip": {"asset_width", "asset_height", "export_count"},
        "offscreen-resource-churn": {
            "surface_count",
            "surface_width",
            "surface_height",
            "framebuffer",
        },
        "storage-compute-lifecycle": {"buffer_size", "dispatch_x", "dispatch_y"},
        "model-import-export": {"triangle_count", "instance_count"},
    }
    unexpected = sorted(set(parameters) - common - case_parameters[kind])
    if unexpected:
        raise CanvasWorkloadError(
            f"{kind} has unexecuted or unsupported parameter(s): " + ", ".join(unexpected)
        )
    missing = sorted(case_parameters[kind] - set(parameters))
    if missing:
        raise CanvasWorkloadError(f"{kind} requires parameter(s): {', '.join(missing)}")
    if parameters.get("dispatch_route", "global") != "global":
        raise CanvasWorkloadError(f"{kind} requires global public API dispatch")
    if kind == "media-frame-conversion":
        count = _positive_int(parameters, "conversion_count", 1, 10_000)
        _positive_int(parameters, "conversion_width", 1, 3_840)
        _positive_int(parameters, "conversion_height", 1, 2_160)
        channels = parameters["channels"]
        if channels not in {1, 3, 4}:
            raise CanvasWorkloadError("media conversion channels must be 1, 3, or 4")
        return count
    if kind == "image-asset-operations":
        _positive_int(parameters, "asset_width", 1, 4_096)
        _positive_int(parameters, "asset_height", 1, 4_096)
        return _positive_int(parameters, "operation_count", 1, 1_000)
    if kind == "png-export-roundtrip":
        _positive_int(parameters, "asset_width", 1, 4_096)
        _positive_int(parameters, "asset_height", 1, 4_096)
        return _positive_int(parameters, "export_count", 1, 100)
    if kind == "offscreen-resource-churn":
        _positive_int(parameters, "surface_width", 1, 1_920)
        _positive_int(parameters, "surface_height", 1, 1_080)
        if not isinstance(parameters["framebuffer"], bool):
            raise CanvasWorkloadError("framebuffer must be boolean")
        return _positive_int(parameters, "surface_count", 1, 64)
    if kind == "storage-compute-lifecycle":
        size = _positive_int(parameters, "buffer_size", 1, 1_000_000)
        dispatch_x = _positive_int(parameters, "dispatch_x", 1, size)
        dispatch_y = _positive_int(parameters, "dispatch_y", 1, size)
        if dispatch_x * dispatch_y > size:
            raise CanvasWorkloadError("compute dispatch cannot exceed buffer_size")
        return dispatch_x * dispatch_y
    triangles = _positive_int(parameters, "triangle_count", 1, 1_000_000)
    instances = _positive_int(parameters, "instance_count", 1, 10_000)
    return triangles * instances


def _declared_draw_records(workload_id: str, parameters: Mapping[str, object]) -> int:
    if workload_id == "primitives-paths-order":
        return _required_primitive_parameters(parameters)
    if workload_id == "images-text-pixels-effects":
        return _required_feature_parameters(parameters)
    if workload_id == "assets-media-models":
        return _required_media_parameters(parameters)
    return 0


def _route(execution_class: ExecutionClass) -> bool:
    if execution_class is ExecutionClass.HEADLESS:
        return True
    if execution_class is ExecutionClass.NATIVE_INTERACTIVE:
        # Passing headless=False is deliberate: CanvasBackend must open its native
        # SDL3 route or report its real capability error. There is no headless retry.
        return False
    raise ExecutionRouteError(
        "Canvas workloads require execution_class='headless' or 'native-interactive'; "
        f"got {execution_class.value!r}"
    )


def build_workload(
    workload_id: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass | str,
) -> WorkloadPlan:
    """Validate and build one static Canvas plan without touching the runtime."""

    if workload_id not in _WORKLOAD_IDS:
        raise CanvasWorkloadError(f"unknown Canvas workload id: {workload_id!r}")
    route = _execution_class(execution_class)
    dispatch_route = str(parameters.get("dispatch_route", "global"))
    if dispatch_route not in _PUBLIC_DISPATCH_ROUTES:
        allowed = sorted(_PUBLIC_DISPATCH_ROUTES)
        raise CanvasWorkloadError(
            f"dispatch_route must be one of {allowed}, got {dispatch_route!r}"
        )
    frames = _positive_int(parameters, "frames", 1, 10_000)
    width = _positive_int(parameters, "width", 64, 3_840)
    height = _positive_int(parameters, "height", 64, 2_160)
    density = _positive_float(parameters, "density", 1.0, 4.0)
    lifecycle_mode, expected_draw_callbacks = _lifecycle_accounting(workload_id, parameters, frames)
    final_width, final_height, final_density = width, height, density
    if lifecycle_mode == "resize-density-churn":
        final_width, final_height, final_density = _resize_sequence(parameters, frames)[-1]
    expected_draw_records = _declared_draw_records(workload_id, parameters)
    required_counters = _required_counters(parameters)
    if route is ExecutionClass.NATIVE_INTERACTIVE and "frames_presented" not in required_counters:
        raise CanvasWorkloadError(
            "native-interactive Canvas workloads require required_counters to include "
            "'frames_presented'"
        )
    return WorkloadPlan(
        workload_id=workload_id,
        execution_class=route,
        headless=_route(route),
        frames=frames,
        width=width,
        height=height,
        density=density,
        final_width=final_width,
        final_height=final_height,
        final_density=final_density,
        dispatch_route=dispatch_route,
        lifecycle_mode=lifecycle_mode,
        expected_draw_callbacks=expected_draw_callbacks,
        expected_draw_records=expected_draw_records,
        parameters=dict(parameters),
    )


def _mutation_offset(gs: Any, plan: WorkloadPlan) -> int:
    mode = str(plan.parameters.get("mutation_mode", "static"))
    if mode == "static":
        return 0
    frame_value = gs.frame_count
    resolved = frame_value() if callable(frame_value) else frame_value
    if isinstance(resolved, bool) or not isinstance(resolved, int):
        raise CanvasWorkloadError("public frame_count must be an integer")
    return resolved // 10 if mode == "low-mutation" else resolved


def _draw_uniform_primitives(gs: Any, plan: WorkloadPlan) -> int:
    count = plan.expected_draw_records
    primitive_kind = str(plan.parameters["primitive_kind"])
    mutation = _mutation_offset(gs, plan)
    gs.fill(255, 72, 72)
    gs.no_stroke()
    drawer = gs.fast() if plan.dispatch_route == "fast" else gs
    for index in range(count - 1):
        x = 6 + (index * 7 + mutation) % max(1, plan.width - 12)
        y = 6 + (index * 11 + mutation) % max(1, plan.height - 12)
        if primitive_kind == "rect":
            drawer.rect(x, y, 6, 6)
        elif primitive_kind == "circle":
            drawer.circle(x + 3, y + 3, 6)
        else:
            drawer.triangle(x, y + 6, x + 3, y, x + 6, y + 6)
    gs.fill(*_SENTINEL_WORK)
    drawer.rect(1, 1, 3, 3)
    return count


def _draw_mixed_primitives(gs: Any, plan: WorkloadPlan) -> int:
    count = plan.expected_draw_records
    style_count = _positive_int(plan.parameters, "style_count", 16, 256)
    mutation = _mutation_offset(gs, plan)
    for index in range(count - 1):
        style = index % style_count
        x = 8 + (index * 7 + mutation) % max(1, plan.width - 16)
        y = 8 + (index * 11 + mutation) % max(1, plan.height - 16)
        gs.fill((style * 29) % 256, (style * 53) % 256, (style * 83) % 256)
        if style % 2:
            gs.stroke((style * 97) % 256, (style * 31) % 256, (style * 19) % 256)
            gs.stroke_weight(1 + style % 3)
        else:
            gs.no_stroke()
        gs.push()
        gs.translate(style % 5 - 2, style % 7 - 3)
        gs.rotate((style % 8) * 0.05)
        gs.shear_x((style % 4) * 0.02)
        if index % 3 == 0:
            gs.rect(x, y, 6, 6)
        elif index % 3 == 1:
            gs.circle(x + 3, y + 3, 6)
        else:
            gs.triangle(x, y + 6, x + 3, y, x + 6, y + 6)
        gs.pop()
    gs.no_stroke()
    gs.fill(*_SENTINEL_WORK)
    gs.rect(1, 1, 3, 3)
    return count


def _draw_line_shape(gs: Any, plan: WorkloadPlan, *, polyline: bool) -> int:
    segments = _positive_int(plan.parameters, "segment_count", 1, 50_000)
    gs.background(0)
    gs.no_fill()
    gs.stroke(255)
    if polyline:
        gs.begin_shape()
        for index in range(segments + 1):
            gs.vertex(
                4 + index % max(1, plan.width - 8),
                4 + (index * 7) % max(1, plan.height - 8),
            )
        gs.end_shape()
    else:
        for index in range(segments):
            x = 4 + index % max(1, plan.width - 8)
            y = 4 + (index * 7) % max(1, plan.height - 8)
            gs.line(x, y, x + 1, y + 1)
    gs.set(1, 1, _SENTINEL_WORK)
    return segments


def _draw_paths(gs: Any, plan: WorkloadPlan) -> int:
    count = plan.expected_draw_records
    segments = _positive_int(plan.parameters, "segments_per_path", 2, 4_096)
    gs.no_stroke()
    for index in range(count - 1):
        offset_x = 6 + (index * 5) % max(1, plan.width - 12)
        offset_y = 6 + (index * 3) % max(1, plan.height - 12)
        gs.fill((index * 41) % 256, (index * 67) % 256, (index * 89) % 256)
        gs.begin_shape()
        gs.vertex(offset_x, offset_y)
        for segment in range(1, segments):
            x = offset_x + segment % 7
            y = offset_y + (segment * 3) % 7
            gs.vertex(x, y)
        gs.end_shape(gs.CLOSE)
    gs.fill(*_SENTINEL_WORK)
    gs.begin_shape()
    gs.vertex(1, 1)
    gs.vertex(5, 1)
    gs.vertex(5, 5)
    gs.vertex(1, 5)
    gs.end_shape(gs.CLOSE)
    return count


def _draw_curves_contours(gs: Any, plan: WorkloadPlan) -> int:
    segments = _positive_int(plan.parameters, "segment_count", 1, 4_096)
    kind = str(plan.parameters["curve_kind"])
    gs.background(0)
    gs.fill(90, 150, 220)
    gs.stroke(255)
    if kind == "arc":
        for index in range(segments):
            size = 8 + index % 24
            gs.arc(plan.width / 2, plan.height / 2, size, size, 0.1, 5.9, gs.PIE)
    else:
        gs.begin_shape()
        gs.vertex(4, 4)
        for index in range(segments):
            x = 8 + index % max(1, plan.width - 16)
            y = 8 + (index * 5) % max(1, plan.height - 16)
            if kind == "quadratic":
                gs.quadratic_vertex(x + 2, y - 2, x, y)
            elif kind == "cubic":
                gs.bezier_vertex(x - 2, y, x + 2, y, x, y)
            else:
                gs.vertex(x, y)
        if kind == "contour-hole":
            gs.vertex(plan.width - 4, plan.height - 4)
            gs.vertex(4, plan.height - 4)
            gs.begin_contour()
            gs.vertex(8, 8)
            gs.vertex(8, plan.height - 8)
            gs.vertex(plan.width - 8, plan.height - 8)
            gs.vertex(plan.width - 8, 8)
            gs.end_contour()
        gs.end_shape(gs.CLOSE)
    gs.set(1, 1, _SENTINEL_WORK)
    return segments


def _draw_ordered_family_stream(
    gs: Any, plan: WorkloadPlan, images: tuple[MutableSpriteImage, ...]
) -> int:
    switches = _positive_int(plan.parameters, "switch_count", 1, 10_000)
    image = images[0]
    for index in range(switches):
        x = 4 + index % max(1, plan.width - 12)
        gs.fill(220, 80, 60)
        gs.rect(x, 4, 4, 4)
        gs.image(image, x, 10, 4, 4, 0, 0, 4, 4)
        gs.fill(255)
        gs.text("order", x, 22)
        gs.filter(gs.INVERT)
    gs.set(1, 1, _SENTINEL_WORK)
    gs.set(2, 1, _SENTINEL_RESTORED)
    return switches * 4


def _draw_nested_clips(gs: Any, plan: WorkloadPlan) -> int:
    count = plan.expected_draw_records
    depth = _positive_int(plan.parameters, "clip_depth", 1, 16)
    segments = _positive_int(plan.parameters, "clip_segments", 3, 4_096)
    center_x = plan.width // 2
    center_y = plan.height // 2
    for level in range(depth):
        radius_x = max(3, plan.width // 2 - (level + 2) * 3)
        radius_y = max(3, plan.height // 2 - (level + 2) * 3)
        with gs.clip_path():
            for segment in range(segments):
                angle = tau * segment / segments
                gs.vertex(center_x + radius_x * cos(angle), center_y + radius_y * sin(angle))
    gs.no_stroke()
    for index in range(count - 2):
        gs.fill((index * 31) % 256, (index * 61) % 256, (index * 101) % 256)
        gs.rect(center_x - 2 + index % 4, center_y - 2 + index % 4, 3, 3)
    gs.fill(*_SENTINEL_WORK)
    gs.rect(center_x, center_y, 3, 3)
    for _ in range(depth):
        gs.end_clip()
    gs.fill(*_SENTINEL_RESTORED)
    gs.rect(1, 1, 3, 3)
    return count


def _draw_primitives_paths_order(
    gs: Any, plan: WorkloadPlan, images: tuple[MutableSpriteImage, ...]
) -> int:
    kind = str(plan.parameters["case_kind"])
    if kind == "uniform-primitives":
        return _draw_uniform_primitives(gs, plan)
    if kind == "mixed-primitives":
        return _draw_mixed_primitives(gs, plan)
    if kind == "independent-lines":
        return _draw_line_shape(gs, plan, polyline=False)
    if kind == "polyline":
        return _draw_line_shape(gs, plan, polyline=True)
    if kind == "paths":
        return _draw_paths(gs, plan)
    if kind == "curves-contours":
        return _draw_curves_contours(gs, plan)
    if kind == "nested-clips":
        return _draw_nested_clips(gs, plan)
    if kind == "ordered-family-stream":
        return _draw_ordered_family_stream(gs, plan, images)
    raise CanvasWorkloadError(f"unsupported primitive/path case kind: {kind!r}")


def _draw_sprite_uniqueness_mutation(
    gs: Any, plan: WorkloadPlan, images: tuple[MutableSpriteImage, ...]
) -> int:
    sprite_count = _positive_int(plan.parameters, "sprite_count", 1, 1_024)
    mutation_count = _positive_int(plan.parameters, "mutation_count", 1, sprite_count)
    gs.background(16, 18, 24)
    gs.no_smooth()
    for index, image in enumerate(images):
        x = (index * 9) % max(1, plan.width - 8)
        y = (index * 5) % max(1, plan.height - 8)
        gs.image(image, x, y, 8, 8, 0, 0, 8, 8)
    for index in range(mutation_count):
        color = _SPRITE_SENTINEL if index == 0 else ((index * 53) % 256, 71, 193, 255)
        images[index].set(1, 0, color)
    gs.image(images[0], plan.width - 2, 1, 1, 1, 1, 0, 1, 1)
    return sprite_count + 1


def _draw_sprite_matrix(gs: Any, plan: WorkloadPlan, images: tuple[MutableSpriteImage, ...]) -> int:
    draw_count = plan.expected_draw_records
    mutation_mode = str(plan.parameters["mutation_mode"])
    source_width = _positive_int(plan.parameters, "source_width", 1, 1_920)
    source_height = _positive_int(plan.parameters, "source_height", 1, 1_080)
    if plan.parameters["sampling"] == "nearest":
        gs.no_smooth()
    else:
        gs.smooth()
    if plan.parameters["tinted"]:
        gs.tint(180, 220, 255, 192)
    for index in range(draw_count):
        image = images[index % len(images)]
        x = (index * 11) % max(1, plan.width - 8)
        y = (index * 7) % max(1, plan.height - 8)
        if plan.parameters["transformed"]:
            gs.push()
            gs.translate(x + 4, y + 4)
            gs.rotate((index % 16) * 0.03)
            gs.image(image, -4, -4, 8, 8, 0, 0, source_width, source_height)
            gs.pop()
        else:
            gs.image(image, x, y, 8, 8, 0, 0, source_width, source_height)
    if mutation_mode == "full":
        images[0].update_pixels(
            generated_rgba_fixture(source_width, source_height, seed=251).pixels
        )
    elif mutation_mode != "unchanged":
        mutation_pixels = (
            max(1, source_width * source_height // 100) if mutation_mode == "one-percent" else 1
        )
        for index in range(mutation_pixels):
            images[0].set(index % source_width, index // source_width, _SPRITE_SENTINEL)
    gs.set(plan.width - 2, 1, _SPRITE_SENTINEL)
    return draw_count


def _draw_text_reuse_script(gs: Any, plan: WorkloadPlan) -> int:
    reused = _positive_int(plan.parameters, "text_reuse_count", 1, 100_000)
    script_text = (
        TEXT_CORPUS["combining"][0],
        TEXT_CORPUS["rtl"][0],
        TEXT_CORPUS["cjk"][0],
        TEXT_CORPUS["multiline"][0],
    )
    gs.background(16, 18, 24)
    gs.fill(255, 255, 255)
    gs.text_size(12)
    reused_text = TEXT_CORPUS["ascii"][2]
    for index in range(reused):
        gs.text(reused_text, 2 + (index * 7) % max(1, plan.width - 12), 12 + (index % 3) * 12)
    for index, value in enumerate(script_text):
        gs.text(value, 2, 12 + (index % 3) * 12)
    gs.set(plan.width - 2, 1, _TEXT_SENTINEL)
    return reused + len(script_text)


def _draw_text_matrix(gs: Any, plan: WorkloadPlan) -> int:
    count = _positive_int(plan.parameters, "label_count", 1, 10_000)
    mode = str(plan.parameters["text_mode"])
    gs.background(16, 18, 24)
    gs.fill(255)
    gs.text_size(_positive_float(plan.parameters, "text_size", 12.0, 512.0))
    clipped = bool(plan.parameters["clipped"])
    if clipped:
        with gs.clip_path():
            gs.vertex(0, 0)
            gs.vertex(plan.width, 0)
            gs.vertex(plan.width, plan.height)
            gs.vertex(0, plan.height)
    corpus = tuple(value for values in TEXT_CORPUS.values() for value in values)
    for index in range(count):
        if mode == "repeated":
            value = TEXT_CORPUS["ascii"][0]
        elif mode == "unique":
            value = f"label-{index:05d}"
        else:
            value = corpus[index % len(corpus)]
        x = 2 + (index * 13) % max(1, plan.width - 8)
        y = 12 + (index * 7) % max(1, plan.height - 12)
        if plan.parameters["transformed"]:
            gs.push()
            gs.translate(x, y)
            gs.rotate((index % 8) * 0.04)
            gs.text(value, 0, 0)
            gs.pop()
        else:
            gs.text(value, x, y)
    if clipped:
        gs.end_clip()
    gs.set(plan.width - 2, 1, _TEXT_SENTINEL)
    return count


def _pixel_fixture_color(index: int) -> tuple[int, int, int, int]:
    offset = (index % (PIXEL_BUFFER.width * PIXEL_BUFFER.height)) * 4
    pixels = PIXEL_BUFFER.pixels
    return (pixels[offset], pixels[offset + 1], pixels[offset + 2], pixels[offset + 3])


def _draw_pixel_read_write_locality(gs: Any, plan: WorkloadPlan) -> int:
    locality_width = _positive_int(plan.parameters, "locality_width", 1, 256)
    locality_height = _positive_int(plan.parameters, "locality_height", 1, 256)
    physical_width = round(plan.width * plan.density)
    physical_height = round(plan.height * plan.density)
    start_x = round(_PIXEL_LOCALITY_ORIGIN[0] * plan.density)
    start_y = round(_PIXEL_LOCALITY_ORIGIN[1] * plan.density)
    if start_x + locality_width > physical_width or start_y + locality_height > physical_height:
        raise CanvasWorkloadError("pixel locality rectangle must fit the physical canvas")
    gs.background(0)
    pixels = gs.load_pixels()
    for index in range(locality_width * locality_height):
        x = start_x + index % locality_width
        y = start_y + index // locality_width
        offset = (y * physical_width + x) * 4
        pixels[offset : offset + 4] = _pixel_fixture_color(index)
    gs.update_pixels(pixels)
    return locality_width * locality_height


def _draw_pixel_readback_matrix(gs: Any, plan: WorkloadPlan) -> int:
    width = _positive_int(plan.parameters, "region_width", 1, 3_840)
    height = _positive_int(plan.parameters, "region_height", 1, 2_160)
    kind = str(plan.parameters["read_kind"])
    gs.background(17, 43, 97)
    if kind == "pixel":
        for index in range(width * height):
            gs.get(index % width, index // width)
    elif kind == "region":
        gs.get(0, 0, width, height)
    elif kind == "full":
        gs.get()
    else:
        gs.load_pixel_bytes()
    gs.set(1, 1, _SENTINEL_WORK)
    return width * height


def _draw_pixel_write_matrix(gs: Any, plan: WorkloadPlan) -> int:
    width = _positive_int(plan.parameters, "region_width", 1, 3_840)
    height = _positive_int(plan.parameters, "region_height", 1, 2_160)
    kind = str(plan.parameters["write_kind"])
    gs.background(0)
    if kind in {"overwrite", "composite"}:
        from gummysnake import Image

        fixture = generated_rgba_fixture(width, height, seed=11)
        image = Image(width, height, fixture.pixels)
        if kind == "overwrite":
            pixels = gs.load_pixels()
            physical_width = round(plan.width * plan.density)
            source = fixture.pixels
            for row in range(height):
                destination_start = row * physical_width * 4
                source_start = row * width * 4
                pixels[destination_start : destination_start + width * 4] = source[
                    source_start : source_start + width * 4
                ]
            gs.update_pixels(pixels)
        else:
            gs.set(0, 0, image)
    else:
        pixels = gs.load_pixels()
        physical_width = round(plan.width * plan.density)
        byte_count = 1 if kind == "one-byte" else width * height * 4
        if kind == "one-pixel":
            byte_count = 4
        elif kind == "row":
            byte_count = width * 4
        for index in range(byte_count):
            pixels[index % len(pixels)] = (index * 29 + 17) % 256
        gs.update_pixels(pixels)
        if physical_width < width:
            raise CanvasWorkloadError("pixel write region exceeds physical canvas width")
    gs.set(1, 1, _SENTINEL_WORK)
    return width * height


def _draw_effect_matrix(gs: Any, plan: WorkloadPlan) -> int:
    family = str(plan.parameters["effect_family"])
    name = str(plan.parameters["effect_name"])
    count = _positive_int(plan.parameters, "operation_count", 1, 10_000)
    gs.background(24, 48, 96)
    if family == "filter":
        mode = getattr(gs, name.upper())
        value = 0.5 if name == "threshold" else 4 if name == "posterize" else None
        for _ in range(count):
            gs.filter(mode, value)
    elif family == "blend":
        mode = getattr(gs, name.upper())
        for index in range(count):
            gs.blend_mode(mode)
            gs.fill(200, 80, 40, 160)
            gs.rect(index % max(1, plan.width - 8), 0, 8, 8)
        gs.blend_mode(gs.BLEND)
    else:
        for index in range(count):
            gs.erase()
            gs.rect(index % max(1, plan.width - 4), 0, 4, 4)
            gs.no_erase()
    gs.set(1, 1, _SENTINEL_WORK)
    return count


def _draw_ordered_effects(gs: Any, plan: WorkloadPlan) -> int:
    if plan.parameters["effect"] != "invert":
        raise CanvasWorkloadError("ordered-effects requires effect='invert'")
    gs.background(*_EFFECT_BACKGROUND)
    gs.set(1, 1, (20, 40, 60, 255))
    gs.filter(gs.INVERT)
    gs.set(1, 1, _EFFECT_OVERLAY)
    return 1


@dataclass(frozen=True, slots=True)
class _FixtureMediaFrame:
    """Minimal decoded-frame surface for the public Rust media conversion helper."""

    payload: bytes
    width: int
    height: int
    channels: int

    @property
    def shape(self) -> tuple[int, int] | tuple[int, int, int]:
        if self.channels == 1:
            return self.height, self.width
        return self.height, self.width, self.channels

    def __buffer__(self, flags: int, /) -> memoryview:
        del flags
        return memoryview(self.payload)

    def __release_buffer__(self, buffer: memoryview, /) -> None:
        del buffer


def _draw_media_frame_conversion(plan: WorkloadPlan) -> int:
    """Convert deterministic grayscale/BGR/BGRA frames through the public Rust helper."""

    from gummysnake.assets.media.frame import convert_frame_bytes

    conversion_count = _positive_int(plan.parameters, "conversion_count", 1, 10_000)
    width = _positive_int(plan.parameters, "conversion_width", 1, 3_840)
    height = _positive_int(plan.parameters, "conversion_height", 1, 2_160)
    channels = cast(int, plan.parameters["channels"])
    if width == 6 and height == 4:
        fixtures = tuple(
            fixture for fixture in _MEDIA_FRAME_FIXTURES if fixture.channels == channels
        )
    else:
        fixtures = (generated_media_frame(width, height, channels, seed=17),)
    for index in range(conversion_count):
        fixture = fixtures[index % len(fixtures)]
        converted = convert_frame_bytes(
            _FixtureMediaFrame(
                fixture.pixels,
                fixture.width,
                fixture.height,
                fixture.channels,
            ),
            fixture.width,
            fixture.height,
            fixture.channels,
        )
        assert_media_frame_rgba(fixture, converted)
    return conversion_count


def _draw_image_asset_operations(gs: Any, plan: WorkloadPlan) -> int:
    from gummysnake import Image

    width = _positive_int(plan.parameters, "asset_width", 1, 4_096)
    height = _positive_int(plan.parameters, "asset_height", 1, 4_096)
    count = _positive_int(plan.parameters, "operation_count", 1, 1_000)
    fixture = generated_rgba_fixture(width, height, seed=23)
    mask_fixture = generated_rgba_fixture(width, height, seed=71)
    for index in range(count):
        image = Image(width, height, fixture.pixels)
        mask = Image(width, height, mask_fixture.pixels)
        copied = image.copy()
        crop_width = max(1, width // 2)
        crop_height = max(1, height // 2)
        cropped = copied.get(0, 0, crop_width, crop_height)
        if not isinstance(cropped, Image):
            raise CanvasWorkloadError("image crop did not return a public Image")
        cropped.resize(max(1, crop_width // 2), max(1, crop_height // 2))
        image.mask(mask)
        image.set(0, 0, cropped)
        filters = (gs.THRESHOLD, gs.GRAY, gs.INVERT, gs.BLUR, gs.POSTERIZE, gs.ERODE, gs.DILATE)
        image_filter = filters[index % len(filters)]
        value = 0.5 if image_filter == gs.THRESHOLD else 4 if image_filter == gs.POSTERIZE else None
        image.filter(image_filter, value)
        if len(image.to_rgba_bytes()) != width * height * 4:
            raise CanvasWorkloadError("image operation changed the declared dimensions")
    gs.set(1, 1, _SENTINEL_WORK)
    return count


def _draw_png_export_roundtrip(gs: Any, plan: WorkloadPlan) -> int:
    from gummysnake import Image, load_image

    width = _positive_int(plan.parameters, "asset_width", 1, 4_096)
    height = _positive_int(plan.parameters, "asset_height", 1, 4_096)
    count = _positive_int(plan.parameters, "export_count", 1, 100)
    fixture = generated_rgba_fixture(width, height, seed=31)
    with TemporaryDirectory(prefix="gummy-snake-canvas-benchmark-") as directory:
        root = Path(directory)
        for index in range(count):
            path = root / f"asset-{index}.png"
            Image(width, height, fixture.pixels).save(path)
            payload = path.read_bytes()
            assert_png_export(payload, width=width, height=height, expected_rgba=fixture.pixels)
            loaded = load_image(path)
            if loaded.to_rgba_bytes() != fixture.pixels:
                raise CanvasWorkloadError("PNG public load did not preserve exact RGBA bytes")
    gs.set(1, 1, _SENTINEL_WORK)
    return count


def _draw_offscreen_resource_churn(gs: Any, plan: WorkloadPlan) -> int:
    count = _positive_int(plan.parameters, "surface_count", 1, 64)
    width = _positive_int(plan.parameters, "surface_width", 1, 1_920)
    height = _positive_int(plan.parameters, "surface_height", 1, 1_080)
    framebuffer = bool(plan.parameters["framebuffer"])
    for index in range(count):
        surface = (
            gs.create_framebuffer(width, height, pixel_density=plan.density, depth=True)
            if framebuffer
            else gs.create_graphics(width, height, pixel_density=plan.density)
        )
        surface.background(index % 256, 32, 64)
        surface.rect(0, 0, max(1, width // 2), max(1, height // 2))
        pixels = surface.to_rgba_bytes()
        expected = round(width * plan.density) * round(height * plan.density) * 4
        if len(pixels) != expected:
            raise CanvasWorkloadError("offscreen surface returned incorrect physical dimensions")
        surface.remove()
    gs.set(1, 1, _SENTINEL_WORK)
    return count


def _draw_storage_compute_lifecycle(gs: Any, plan: WorkloadPlan) -> int:
    size = _positive_int(plan.parameters, "buffer_size", 1, 1_000_000)
    dispatch_x = _positive_int(plan.parameters, "dispatch_x", 1, size)
    dispatch_y = _positive_int(plan.parameters, "dispatch_y", 1, size)
    buffer = gs.create_storage_buffer(size, dtype="int")
    shader = gs.create_compute_shader(
        source=f"""
@group(0) @binding(0) var<storage, read_write> values: array<i32>;
@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {{
    let index = gid.y * {dispatch_x}u + gid.x;
    values[index] = i32(index + 1u);
}}
""",
        label="canvas-benchmark-deterministic-compute",
    )
    gs.dispatch_compute(shader, dispatch_x, dispatch_y, values=buffer)
    values = gs.read_storage_buffer(buffer)
    work = dispatch_x * dispatch_y
    if values[:work] != tuple(range(1, work + 1)):
        raise CanvasWorkloadError("storage/compute public path produced incorrect values")
    buffer.close()
    gs.set(1, 1, _SENTINEL_WORK)
    return work


def _generated_obj(triangle_count: int) -> bytes:
    lines = ["# deterministic generated Canvas benchmark model"]
    for triangle in range(triangle_count):
        x = triangle % 256
        y = triangle // 256
        lines.extend(
            (
                f"v {x}.0 {y}.0 0.0",
                f"v {x + 1}.0 {y}.0 0.0",
                f"v {x}.0 {y + 1}.0 0.0",
            )
        )
        base = triangle * 3 + 1
        lines.append(f"f {base} {base + 1} {base + 2}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _draw_model_import_export(gs: Any, plan: WorkloadPlan) -> int:
    triangles = _positive_int(plan.parameters, "triangle_count", 1, 1_000_000)
    instances = _positive_int(plan.parameters, "instance_count", 1, 10_000)
    with TemporaryDirectory(prefix="gummy-snake-model-benchmark-") as directory:
        root = Path(directory)
        source = root / "generated.obj"
        source.write_bytes(_generated_obj(triangles))
        model = gs.load_model(source, normalize=True)
        drawer = gs.fast()
        for index in range(instances):
            drawer.push()
            drawer.translate(index % 16, index // 16, 0)
            drawer.model(model)
            drawer.pop()
        obj_path = gs.save_obj(model, root / "export.obj")
        stl_path = gs.save_stl(model, root / "export.stl")
        if not obj_path.read_bytes().startswith(b"#"):
            raise CanvasWorkloadError("OBJ export did not produce an OBJ payload")
        if len(stl_path.read_bytes()) < 84:
            raise CanvasWorkloadError("STL export did not produce a complete payload")
    gs.set(1, 1, _SENTINEL_WORK)
    return triangles * instances


def _draw_assets_media_models(gs: Any, plan: WorkloadPlan) -> int:
    kind = str(plan.parameters["case_kind"])
    if kind == "media-frame-conversion":
        return _draw_media_frame_conversion(plan)
    if kind == "image-asset-operations":
        return _draw_image_asset_operations(gs, plan)
    if kind == "png-export-roundtrip":
        return _draw_png_export_roundtrip(gs, plan)
    if kind == "offscreen-resource-churn":
        return _draw_offscreen_resource_churn(gs, plan)
    if kind == "storage-compute-lifecycle":
        return _draw_storage_compute_lifecycle(gs, plan)
    if kind == "model-import-export":
        return _draw_model_import_export(gs, plan)
    raise CanvasWorkloadError(f"unsupported asset/media/model case kind: {kind!r}")


def _draw_images_text_pixels_effects(
    gs: Any, plan: WorkloadPlan, images: tuple[MutableSpriteImage, ...]
) -> int:
    kind = str(plan.parameters["case_kind"])
    if kind == "sprite-uniqueness-mutation":
        return _draw_sprite_uniqueness_mutation(gs, plan, images)
    if kind == "sprite-matrix":
        return _draw_sprite_matrix(gs, plan, images)
    if kind == "text-reuse-script":
        return _draw_text_reuse_script(gs, plan)
    if kind == "text-matrix":
        return _draw_text_matrix(gs, plan)
    if kind == "pixel-read-write-locality":
        return _draw_pixel_read_write_locality(gs, plan)
    if kind == "pixel-readback-matrix":
        return _draw_pixel_readback_matrix(gs, plan)
    if kind == "pixel-write-matrix":
        return _draw_pixel_write_matrix(gs, plan)
    if kind == "ordered-effects":
        return _draw_ordered_effects(gs, plan)
    if kind == "effect-matrix":
        return _draw_effect_matrix(gs, plan)
    raise CanvasWorkloadError(f"unsupported image/text/pixel/effect case kind: {kind!r}")


def _callbacks(
    plan: WorkloadPlan, gs: Any
) -> tuple[Callable[[], None], Callable[[], None], _CallbackAccounting]:
    images: tuple[MutableSpriteImage, ...] = ()
    accounting = _CallbackAccounting()

    def setup(api: Any = gs) -> None:
        nonlocal images
        accounting.setup_calls += 1
        api.enable_performance_diagnostics(True, reset=True)
        api.enable_frame_pacing_diagnostics(True, reset=True)
        if (
            plan.workload_id == "assets-media-models"
            and plan.parameters.get("case_kind") == "model-import-export"
        ):
            api.create_canvas(plan.width, plan.height, gs.WEBGL, pixel_density=plan.density)
        else:
            api.create_canvas(plan.width, plan.height, pixel_density=plan.density)
        api.frame_rate(_positive_float(plan.parameters, "frame_rate", 60.0, 1_000.0))
        api.background(0)
        if plan.workload_id == "lifecycle-hidpi":
            if plan.lifecycle_mode in {
                "empty-loop",
                "continuous-clear-loop",
                "dynamic-frame-rate",
                "resize-density-churn",
            }:
                api.loop()
            elif plan.lifecycle_mode == "explicit-redraw":
                api.no_loop()
                api.redraw()
        if plan.workload_id == "images-text-pixels-effects" and str(
            plan.parameters["case_kind"]
        ) in {"sprite-uniqueness-mutation", "sprite-matrix"}:
            if str(plan.parameters["case_kind"]) == "sprite-matrix":
                from gummysnake import Image

                count = _positive_int(plan.parameters, "unique_images", 1, 128)
                source_width = _positive_int(plan.parameters, "source_width", 1, 1_920)
                source_height = _positive_int(plan.parameters, "source_height", 1, 1_080)
                images = tuple(
                    cast(
                        MutableSpriteImage,
                        Image(
                            source_width,
                            source_height,
                            generated_rgba_fixture(source_width, source_height, seed=index).pixels,
                        ),
                    )
                    for index in range(count)
                )
            else:
                count = _positive_int(plan.parameters, "sprite_count", 1, 1_024)
                images = tuple(cast(MutableSpriteImage, sprite_image()) for _ in range(count))
        elif (
            plan.workload_id == "primitives-paths-order"
            and str(plan.parameters["case_kind"]) == "ordered-family-stream"
        ):
            images = (cast(MutableSpriteImage, sprite_image()),)

    def draw(api: Any = gs) -> None:
        accounting.draw_calls += 1
        if plan.workload_id == "lifecycle-hidpi":
            if plan.lifecycle_mode != "empty-loop":
                api.background(0)
            if plan.lifecycle_mode == "no-loop-idle":
                api.no_loop()
            elif plan.lifecycle_mode == "dynamic-frame-rate":
                sequence = _number_sequence(
                    plan.parameters,
                    "frame_rate_sequence",
                    length=plan.frames,
                    maximum=1_000.0,
                )
                api.frame_rate(sequence[accounting.draw_calls - 1])
            elif plan.lifecycle_mode == "resize-density-churn":
                width, height, density = _resize_sequence(plan.parameters, plan.frames)[
                    accounting.draw_calls - 1
                ]
                api.resize_canvas(width, height, pixel_density=density)
        elif plan.workload_id == "primitives-paths-order":
            accounting.draw_records += _draw_primitives_paths_order(api, plan, images)
        elif plan.workload_id == "images-text-pixels-effects":
            accounting.draw_records += _draw_images_text_pixels_effects(api, plan, images)
        else:
            accounting.draw_records += _draw_assets_media_models(api, plan)

    return setup, draw, accounting


def _run_public_sketch(
    gs: Any, plan: WorkloadPlan
) -> tuple[CompletedCanvasContext, _CallbackAccounting]:
    setup, draw, accounting = _callbacks(plan, gs)
    if plan.dispatch_route != "object":
        return (
            gs.run(setup=setup, draw=draw, headless=plan.headless, max_frames=plan.frames),
            accounting,
        )

    class CanvasBenchmarkSketch(gs.Sketch):
        def setup(self) -> None:
            cast(Callable[[Any], None], setup)(self)

        def draw(self) -> None:
            cast(Callable[[Any], None], draw)(self)

    return CanvasBenchmarkSketch(headless=plan.headless).run(max_frames=plan.frames), accounting


def _assert_callback_frame_accounting(
    context: CompletedCanvasContext, plan: WorkloadPlan, accounting: _CallbackAccounting
) -> None:
    """Require the dispatched callbacks and completed frames to match the case contract."""

    if accounting.setup_calls != 1:
        raise CanvasWorkloadError(
            f"{plan.workload_id} setup callbacks expected 1, got {accounting.setup_calls}"
        )
    if accounting.draw_calls != plan.expected_draw_callbacks:
        raise CanvasWorkloadError(
            f"{plan.workload_id} draw callbacks expected {plan.expected_draw_callbacks}, "
            f"got {accounting.draw_calls}"
        )
    if context.frame_count != plan.expected_draw_callbacks:
        raise CanvasWorkloadError(
            f"{plan.workload_id} completed frames expected {plan.expected_draw_callbacks}, "
            f"got {context.frame_count}"
        )
    expected_records = plan.expected_draw_records * plan.expected_draw_callbacks
    if accounting.draw_records != expected_records:
        raise CanvasWorkloadError(
            f"{plan.workload_id} declared draw records expected {expected_records}, "
            f"got {accounting.draw_records}"
        )


def _feature_output_sentinels(plan: WorkloadPlan) -> tuple[PixelSentinel, ...]:
    """Return exact feature-case pixels from the ordered public command stream."""

    density = plan.density
    kind = str(plan.parameters["case_kind"])
    if kind == "sprite-uniqueness-mutation":
        return (PixelSentinel(round((plan.width - 2) * density), round(density), _SPRITE_SENTINEL),)
    if kind == "text-reuse-script":
        return (PixelSentinel(round((plan.width - 2) * density), round(density), _TEXT_SENTINEL),)
    if kind == "pixel-read-write-locality":
        locality_width = _positive_int(plan.parameters, "locality_width", 1, 256)
        locality_height = _positive_int(plan.parameters, "locality_height", 1, 256)
        start_x = round(_PIXEL_LOCALITY_ORIGIN[0] * density)
        start_y = round(_PIXEL_LOCALITY_ORIGIN[1] * density)
        count = locality_width * locality_height
        return (
            PixelSentinel(start_x, start_y, _pixel_fixture_color(0)),
            PixelSentinel(
                start_x + locality_width - 1,
                start_y + locality_height - 1,
                _pixel_fixture_color(count - 1),
            ),
        )
    if kind == "ordered-effects":
        return (
            PixelSentinel(round(6 * density), round(6 * density), (245, 235, 225, 255)),
            PixelSentinel(round(density), round(density), _EFFECT_OVERLAY),
        )
    if kind == "sprite-matrix":
        return (PixelSentinel(round((plan.width - 2) * density), round(density), _SPRITE_SENTINEL),)
    if kind == "text-matrix":
        return (PixelSentinel(round((plan.width - 2) * density), round(density), _TEXT_SENTINEL),)
    if kind in {"pixel-readback-matrix", "pixel-write-matrix", "effect-matrix"}:
        return (PixelSentinel(round(density), round(density), _SENTINEL_WORK),)
    raise CanvasWorkloadError(f"unsupported image/text/pixel/effect case kind: {kind!r}")


def _output_sentinels(plan: WorkloadPlan) -> tuple[PixelSentinel, ...]:
    """Return final public-pixel sentinels for the executed case."""

    if plan.workload_id == "images-text-pixels-effects":
        return _feature_output_sentinels(plan)
    if plan.workload_id == "assets-media-models":
        if str(plan.parameters["case_kind"]) == "media-frame-conversion":
            return ()
        return (
            PixelSentinel(round(plan.final_density), round(plan.final_density), _SENTINEL_WORK),
        )
    if plan.workload_id != "primitives-paths-order":
        return ()
    density = plan.density
    if str(plan.parameters["case_kind"]) == "paths":
        work_x = work_y = round(2 * density)
    elif str(plan.parameters["case_kind"]) == "nested-clips":
        work_x = round((plan.width // 2) * density)
        work_y = round((plan.height // 2) * density)
    else:
        work_x = work_y = round(density)
    sentinels = [PixelSentinel(work_x, work_y, _SENTINEL_WORK)]
    if str(plan.parameters["case_kind"]) == "nested-clips":
        sentinels.append(PixelSentinel(round(density), round(density), _SENTINEL_RESTORED))
    return tuple(sentinels)


def _required_counters(parameters: Mapping[str, object]) -> tuple[str, ...]:
    raw = parameters.get("required_counters", ())
    if not isinstance(raw, (list, tuple)) or not all(
        isinstance(item, str) and item for item in raw
    ):
        raise CanvasWorkloadError(
            "required_counters must be a list or tuple of public counter names"
        )
    return tuple(raw)


def dispatch(
    workload_id: str,
    parameters: Mapping[str, object],
    execution_class: ExecutionClass | str,
) -> WorkloadRun:
    """Run one bounded actual Canvas sketch using a declared execution route.

    ``native-interactive`` always calls the public runtime with ``headless=False``
    and requires its bounded frames to reach the public presentation counter. Missing
    native capability propagates the runtime's actionable capability error and is
    never retried headlessly.
    """

    validate_manifest()
    plan = build_workload(workload_id, parameters, execution_class)
    import gummysnake as gs

    context, accounting = _run_public_sketch(gs, plan)
    _assert_callback_frame_accounting(context, plan, accounting)
    pixels = bytes(context.load_pixel_bytes())
    assert_canvas_state(
        context,
        logical_width=plan.final_width,
        logical_height=plan.final_height,
        density=plan.final_density,
        frame_count=plan.expected_draw_callbacks,
    )
    assert_hidpi_dimensions(
        context,
        pixels,
        logical_width=plan.final_width,
        logical_height=plan.final_height,
        density=plan.final_density,
    )
    assert_ordered_layers(
        pixels,
        round(plan.final_width * plan.final_density),
        _output_sentinels(plan),
    )
    diagnostics = capture_canvas_diagnostics(
        context,
        required=_required_counters(plan.parameters),
        execution_class=plan.execution_class.value,
        physical_desktop_requested=not plan.headless,
    )
    if not plan.headless:
        assert_presented_frames(diagnostics.counters, plan.expected_draw_callbacks)
    return WorkloadRun(
        plan=plan,
        frame_count=int(context.frame_count),
        pixels=pixels,
        diagnostics=diagnostics,
        setup_callbacks=accounting.setup_calls,
        draw_callbacks=accounting.draw_calls,
        draw_records=accounting.draw_records,
        physical_desktop_requested=not plan.headless,
    )


__all__ = [
    "CanvasWorkloadError",
    "ExecutionRouteError",
    "WorkloadPlan",
    "WorkloadRun",
    "build_workload",
    "dispatch",
]
