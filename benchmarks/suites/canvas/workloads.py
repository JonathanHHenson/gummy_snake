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
from typing import Any, Protocol

from benchmarks.governance import ExecutionClass

from .diagnostics import DiagnosticsSnapshot, capture_renderer_diagnostics
from .fixtures import TEXT_CORPUS, sprite_image, validate_manifest
from .oracles import assert_hidpi_dimensions


class CanvasWorkloadError(ValueError):
    """A static Canvas workload declaration cannot be constructed safely."""


class ExecutionRouteError(CanvasWorkloadError):
    """A request would use an unsupported or silently substituted execution route."""


class CompletedCanvasContext(Protocol):
    """Public post-run context operations consumed by the dispatcher."""

    width: int
    height: int
    frame_count: int

    def pixel_density(self) -> float: ...

    def load_pixel_bytes(self) -> bytes: ...

    def renderer_performance_counters(self) -> dict[str, object]: ...


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
    parameters: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class WorkloadRun:
    """Observable result of one real bounded workload execution."""

    plan: WorkloadPlan
    frame_count: int
    pixels: bytes
    diagnostics: DiagnosticsSnapshot
    physical_desktop_requested: bool


_WORKLOAD_IDS = frozenset(
    {
        "lifecycle-hidpi",
        "primitives-paths-order",
        "images-text-pixels-effects",
    }
)
_PUBLIC_DISPATCH_ROUTES = frozenset({"global", "object", "fast"})


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
    """Validate and build one static Canvas plan without touching the runtime.

    Catalogs may include matrix metadata such as ``density_matrix`` or
    ``draw_count_matrix``. The scalar values (``density``, ``draw_count``, and so
    on) select the bounded case executed by this invocation.
    """

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
    return WorkloadPlan(
        workload_id=workload_id,
        execution_class=route,
        headless=_route(route),
        frames=frames,
        width=width,
        height=height,
        density=density,
        dispatch_route=dispatch_route,
        parameters=dict(parameters),
    )


def _draw_primitives(gs: Any, plan: WorkloadPlan) -> None:
    count = _positive_int(plan.parameters, "draw_count", 32, 100_000)
    clip_depth = _positive_int(plan.parameters, "clip_depth", 1, 16)
    gs.fill(255, 72, 72)
    gs.no_stroke()
    for index in range(count):
        x = (index * 7) % max(1, plan.width - 8)
        y = (index * 11) % max(1, plan.height - 8)
        mode = index % 3
        if mode == 0:
            gs.rect(x, y, 6, 6)
        elif mode == 1:
            gs.circle(x + 3, y + 3, 6)
        else:
            gs.triangle(x, y + 6, x + 3, y, x + 6, y + 6)

    for _ in range(clip_depth):
        with gs.clip_path():
            gs.vertex(1, 1)
            gs.vertex(plan.width - 1, 1)
            gs.vertex(plan.width - 1, plan.height - 1)
            gs.vertex(1, plan.height - 1)
    gs.fill(31, 132, 217)
    gs.rect(2, 2, max(1, plan.width - 4), max(1, plan.height - 4))
    for _ in range(clip_depth):
        gs.end_clip()

    gs.begin_shape()
    gs.vertex(2, plan.height - 2)
    gs.vertex(plan.width // 2, max(1, plan.height - 12))
    gs.vertex(plan.width - 2, plan.height - 2)
    gs.end_shape(gs.CLOSE)


def _draw_fast_primitives(gs: Any, plan: WorkloadPlan) -> None:
    count = _positive_int(plan.parameters, "draw_count", 32, 100_000)
    gs.fill(255, 72, 72)
    gs.no_stroke()
    fast = gs.fast()
    for index in range(count):
        x = (index * 7) % max(1, plan.width - 8)
        y = (index * 11) % max(1, plan.height - 8)
        if index % 3 == 0:
            fast.rect(x, y, 6, 6)
        elif index % 3 == 1:
            fast.circle(x + 3, y + 3, 6)
        else:
            fast.triangle(x, y + 6, x + 3, y, x + 6, y + 6)


def _draw_images_text_pixels_effects(gs: Any, plan: WorkloadPlan, image: object) -> None:
    image_count = _positive_int(plan.parameters, "image_count", 16, 10_000)
    gs.background(16, 18, 24)
    for index in range(image_count):
        x = (index * 9) % max(1, plan.width - 8)
        y = (index * 5) % max(1, plan.height - 8)
        gs.image(image, x, y, 8, 8, 0, 0, 8, 8)
    gs.fill(255, 255, 255)
    gs.text_size(_positive_int(plan.parameters, "text_size", 12, 128))
    gs.text(TEXT_CORPUS["ascii"][0], 2, max(12, plan.height // 2))
    gs.fill(244, 80, 72)
    gs.rect(0, max(0, plan.height - 6), min(12, plan.width), 6)

    pixels = gs.load_pixels()
    pixels[0] = 17
    pixels[1] = 29
    pixels[2] = 47
    pixels[3] = 255
    gs.update_pixels(pixels)
    if str(plan.parameters.get("effect", "none")) == "gray":
        gs.filter(gs.GRAY)
    gs.fill(255, 255, 255)
    gs.text(TEXT_CORPUS["ascii"][1], 2, max(12, plan.height - 2))


def _callbacks(plan: WorkloadPlan, gs: Any) -> tuple[Callable[[], None], Callable[[], None]]:
    image: object | None = None

    def setup() -> None:
        nonlocal image
        gs.create_canvas(plan.width, plan.height, pixel_density=plan.density)
        gs.frame_rate(_positive_float(plan.parameters, "frame_rate", 60.0, 1_000.0))
        gs.background(0)
        if plan.workload_id == "images-text-pixels-effects":
            image = sprite_image()

    def draw() -> None:
        if plan.workload_id == "lifecycle-hidpi":
            gs.background(0)
            if bool(plan.parameters.get("redraw_burst", False)):
                gs.redraw()
        elif plan.workload_id == "primitives-paths-order":
            if plan.dispatch_route == "fast":
                _draw_fast_primitives(gs, plan)
            else:
                _draw_primitives(gs, plan)
        else:
            if image is None:
                raise RuntimeError("image workload draw ran before setup created its image")
            _draw_images_text_pixels_effects(gs, plan, image)

    return setup, draw


def _run_public_sketch(gs: Any, plan: WorkloadPlan) -> CompletedCanvasContext:
    setup, draw = _callbacks(plan, gs)
    if plan.dispatch_route != "object":
        return gs.run(setup=setup, draw=draw, headless=plan.headless, max_frames=plan.frames)

    class CanvasBenchmarkSketch(gs.Sketch):
        def setup(self) -> None:
            setup()

        def draw(self) -> None:
            draw()

    return CanvasBenchmarkSketch(headless=plan.headless).run(max_frames=plan.frames)


def _required_counters(parameters: Mapping[str, object]) -> tuple[str, ...]:
    raw = parameters.get("required_counters", ())
    if not isinstance(raw, (list, tuple)) or not all(isinstance(item, str) for item in raw):
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

    ``native-interactive`` always calls the public runtime with ``headless=False``.
    Success therefore means the installed runtime accepted a native-window route;
    it does **not** claim compositor or physical scanout qualification. Missing
    native capability propagates the runtime's actionable capability error and is
    never retried headlessly.
    """

    validate_manifest()
    plan = build_workload(workload_id, parameters, execution_class)
    import gummysnake as gs

    context = _run_public_sketch(gs, plan)
    pixels = bytes(context.load_pixel_bytes())
    assert_hidpi_dimensions(
        context,
        pixels,
        logical_width=plan.width,
        logical_height=plan.height,
        density=plan.density,
    )
    diagnostics = capture_renderer_diagnostics(
        context, required=_required_counters(plan.parameters)
    )
    return WorkloadRun(
        plan=plan,
        frame_count=int(context.frame_count),
        pixels=pixels,
        diagnostics=diagnostics,
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
