"""Static Canvas workload plans and their bounded production-path dispatcher.

``dispatch(workload_id, parameters, execution_class)`` is the intended worker
integration point. It constructs real Gummy Snake callbacks and runs them through
``gs.run`` (or the public ``Sketch`` facade for object mode).  It intentionally
does not time, emulate, or substitute a renderer route; the benchmark worker owns
timing around this bounded work.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import cos, sin, tau
from typing import Any, Protocol, cast

from benchmarks.governance import ExecutionClass

from .diagnostics import DiagnosticsSnapshot, capture_renderer_diagnostics
from .fixtures import (
    MEDIA_FRAME_BGR,
    MEDIA_FRAME_BGRA,
    MEDIA_FRAME_GRAY,
    PIXEL_BUFFER,
    TEXT_CORPUS,
    MediaFrameFixture,
    sprite_image,
    validate_manifest,
)
from .oracles import (
    PixelSentinel,
    assert_hidpi_dimensions,
    assert_media_frame_rgba,
    assert_ordered_layers,
    assert_presented_frames,
)


class CanvasWorkloadError(ValueError):
    """A static Canvas workload declaration cannot be constructed safely."""


class ExecutionRouteError(CanvasWorkloadError):
    """A request would use an unsupported or silently substituted execution route."""


class MutableSpriteImage(Protocol):
    """Public mutable-image operation required by the sprite mutation case."""

    def set(self, x: int, y: int, value: tuple[int, int, int, int]) -> None: ...


class CompletedCanvasContext(Protocol):
    """Public post-run context operations consumed by the dispatcher."""

    width: int
    height: int
    frame_count: int

    def pixel_density(self) -> float: ...

    def load_pixel_bytes(self) -> bytes: ...

    def renderer_performance_counters(self) -> dict[str, object]: ...


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
_LIFECYCLE_MODES = frozenset({"continuous-clear-loop", "explicit-redraw", "no-loop-idle"})
_PRIMITIVE_CASE_KINDS = frozenset(
    {"uniform-primitives", "mixed-primitives", "paths", "nested-clips"}
)
_MEDIA_CASE_KINDS = frozenset({"media-frame-conversion"})
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
    }
)
_SENTINEL_WORK = (17, 43, 97, 255)
_SENTINEL_RESTORED = (229, 157, 43, 255)
_SPRITE_SENTINEL = (17, 43, 97, 255)
_TEXT_SENTINEL = (229, 157, 43, 255)
_EFFECT_BACKGROUND = (10, 20, 30, 255)
_EFFECT_OVERLAY = (17, 43, 97, 255)
_PIXEL_LOCALITY_ORIGIN = (2, 2)


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
    default_draws = frames if mode == "continuous-clear-loop" else 1
    expected_draws = _positive_int(parameters, "expected_draw_callbacks", default_draws, frames)
    if mode == "continuous-clear-loop" and expected_draws != frames:
        raise CanvasWorkloadError(
            "continuous-clear-loop requires expected_draw_callbacks to equal frames"
        )
    if mode != "continuous-clear-loop":
        if frames < 2:
            raise CanvasWorkloadError(f"{mode} requires at least two bounded scheduling ticks")
        if expected_draws != 1:
            raise CanvasWorkloadError(f"{mode} requires exactly one draw callback")
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
        "uniform-primitives": {"primitive_kind"},
        "mixed-primitives": {"style_count"},
        "paths": {"segments_per_path"},
        "nested-clips": {"clip_depth", "clip_segments"},
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
    elif kind == "mixed-primitives":
        _positive_int(parameters, "style_count", 16, 256)
    elif kind == "paths":
        _positive_int(parameters, "segments_per_path", 2, 4_096)
    else:
        if draw_count < 2:
            raise CanvasWorkloadError("nested-clips requires draw_count of at least 2")
        _positive_int(parameters, "clip_depth", 1, 16)
        _positive_int(parameters, "clip_segments", 3, 4_096)
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
        "sprite-uniqueness-mutation": {"sprite_count", "mutation_count"},
        "text-reuse-script": {"text_reuse_count"},
        "pixel-read-write-locality": {"locality_width", "locality_height"},
        "ordered-effects": {"effect"},
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
    elif parameters["effect"] != "invert":
        raise CanvasWorkloadError("ordered-effects requires effect='invert'")
    elif draw_count != 1:
        raise CanvasWorkloadError("ordered-effects requires draw_count to equal one effect pass")
    if not _required_counters(parameters):
        raise CanvasWorkloadError(
            "image/text/pixel/effect cases require declared required_counters"
        )
    return draw_count


def _required_media_parameters(parameters: Mapping[str, object]) -> int:
    """Validate the generated native media-frame conversion workload."""

    kind = parameters.get("case_kind")
    if not isinstance(kind, str) or kind not in _MEDIA_CASE_KINDS:
        raise CanvasWorkloadError(
            f"case_kind must be one of {sorted(_MEDIA_CASE_KINDS)}, got {kind!r}"
        )
    allowed = {
        "case_kind",
        "conversion_count",
        "frames",
        "width",
        "height",
        "density",
        "frame_rate",
        "dispatch_route",
        "required_counters",
    }
    unexpected = sorted(set(parameters) - allowed)
    if unexpected:
        raise CanvasWorkloadError(
            "media-frame-conversion has unexecuted or unsupported parameter(s): "
            + ", ".join(unexpected)
        )
    if parameters.get("dispatch_route", "global") != "global":
        raise CanvasWorkloadError("media-frame-conversion requires global public API dispatch")
    return _positive_int(parameters, "conversion_count", 1, 100_000)


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
        dispatch_route=dispatch_route,
        lifecycle_mode=lifecycle_mode,
        expected_draw_callbacks=expected_draw_callbacks,
        expected_draw_records=expected_draw_records,
        parameters=dict(parameters),
    )


def _draw_uniform_primitives(gs: Any, plan: WorkloadPlan) -> int:
    count = plan.expected_draw_records
    primitive_kind = str(plan.parameters["primitive_kind"])
    gs.fill(255, 72, 72)
    gs.no_stroke()
    drawer = gs.fast() if plan.dispatch_route == "fast" else gs
    for index in range(count - 1):
        x = 6 + (index * 7) % max(1, plan.width - 12)
        y = 6 + (index * 11) % max(1, plan.height - 12)
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
    for index in range(count - 1):
        style = index % style_count
        x = 8 + (index * 7) % max(1, plan.width - 16)
        y = 8 + (index * 11) % max(1, plan.height - 16)
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


def _draw_primitives_paths_order(gs: Any, plan: WorkloadPlan) -> int:
    kind = str(plan.parameters["case_kind"])
    if kind == "uniform-primitives":
        return _draw_uniform_primitives(gs, plan)
    if kind == "mixed-primitives":
        return _draw_mixed_primitives(gs, plan)
    if kind == "paths":
        return _draw_paths(gs, plan)
    if kind == "nested-clips":
        return _draw_nested_clips(gs, plan)
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

    def tobytes(self) -> bytes:
        return self.payload


def _draw_media_frame_conversion(plan: WorkloadPlan) -> int:
    """Convert reviewed grayscale/BGR/BGRA frames through the public Rust helper."""

    from gummysnake.assets.media.frame import convert_frame_bytes

    conversion_count = _positive_int(plan.parameters, "conversion_count", 1, 100_000)
    for index in range(conversion_count):
        fixture = _MEDIA_FRAME_FIXTURES[index % len(_MEDIA_FRAME_FIXTURES)]
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


def _draw_images_text_pixels_effects(
    gs: Any, plan: WorkloadPlan, images: tuple[MutableSpriteImage, ...]
) -> int:
    kind = str(plan.parameters["case_kind"])
    if kind == "sprite-uniqueness-mutation":
        return _draw_sprite_uniqueness_mutation(gs, plan, images)
    if kind == "text-reuse-script":
        return _draw_text_reuse_script(gs, plan)
    if kind == "pixel-read-write-locality":
        return _draw_pixel_read_write_locality(gs, plan)
    if kind == "ordered-effects":
        return _draw_ordered_effects(gs, plan)
    raise CanvasWorkloadError(f"unsupported image/text/pixel/effect case kind: {kind!r}")


def _callbacks(
    plan: WorkloadPlan, gs: Any
) -> tuple[Callable[[], None], Callable[[], None], _CallbackAccounting]:
    images: tuple[MutableSpriteImage, ...] = ()
    accounting = _CallbackAccounting()

    def setup() -> None:
        nonlocal images
        accounting.setup_calls += 1
        gs.create_canvas(plan.width, plan.height, pixel_density=plan.density)
        gs.frame_rate(_positive_float(plan.parameters, "frame_rate", 60.0, 1_000.0))
        gs.background(0)
        if plan.workload_id == "lifecycle-hidpi":
            if plan.lifecycle_mode == "continuous-clear-loop":
                gs.loop()
            elif plan.lifecycle_mode == "explicit-redraw":
                gs.no_loop()
                gs.redraw()
        if (
            plan.workload_id == "images-text-pixels-effects"
            and str(plan.parameters["case_kind"]) == "sprite-uniqueness-mutation"
        ):
            count = _positive_int(plan.parameters, "sprite_count", 1, 1_024)
            images = tuple(cast(MutableSpriteImage, sprite_image()) for _ in range(count))

    def draw() -> None:
        accounting.draw_calls += 1
        if plan.workload_id == "lifecycle-hidpi":
            gs.background(0)
            if plan.lifecycle_mode == "no-loop-idle":
                gs.no_loop()
        elif plan.workload_id == "primitives-paths-order":
            accounting.draw_records += _draw_primitives_paths_order(gs, plan)
        elif plan.workload_id == "images-text-pixels-effects":
            accounting.draw_records += _draw_images_text_pixels_effects(gs, plan, images)
        else:
            accounting.draw_records += _draw_media_frame_conversion(plan)

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
            setup()

        def draw(self) -> None:
            draw()

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
    raise CanvasWorkloadError(f"unsupported image/text/pixel/effect case kind: {kind!r}")


def _output_sentinels(plan: WorkloadPlan) -> tuple[PixelSentinel, ...]:
    """Return final public-pixel sentinels for the executed case."""

    if plan.workload_id == "images-text-pixels-effects":
        return _feature_output_sentinels(plan)
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
    assert_hidpi_dimensions(
        context,
        pixels,
        logical_width=plan.width,
        logical_height=plan.height,
        density=plan.density,
    )
    assert_ordered_layers(
        pixels,
        round(plan.width * plan.density),
        _output_sentinels(plan),
    )
    diagnostics = capture_renderer_diagnostics(
        context, required=_required_counters(plan.parameters)
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
