"""Canvas replay helpers for Rust-backed ECS physical execution."""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.runtime_views import Entity
from gummysnake.ecs.schema_helpers import _event_payload_from_bridge
from gummysnake.ecs.world_helpers import _current_delta_time, _current_key_down
from gummysnake.exceptions import SystemExecutionError

if TYPE_CHECKING:
    from gummysnake.ecs.world import EcsWorld


_STYLE_COMMANDS = frozenset(
    {
        "fill",
        "no_fill",
        "stroke",
        "no_stroke",
        "stroke_weight",
        "erase",
        "no_erase",
        "blend_mode",
    }
)


@dataclass
class _CanvasReplayState:
    """Renderer state required to preserve ordered compact fill replay."""

    context: Any
    renderer: Any
    primitive_batch: Any
    constants: Any
    direct_fill_active: bool = False
    primitive_records: Any = None
    matrix_payload: Any = None
    current_fill: Any = None
    direct_fill_allowed: bool = False

    def __post_init__(self) -> None:
        self.refresh_direct_fill_state()

    def refresh_direct_fill_state(self) -> None:
        """Synchronize compact-fill eligibility after a replayed command."""
        style = self.context.state.style
        self.primitive_records = self.primitive_batch.records
        self.matrix_payload = self.renderer._matrix_payload(self.context.state.transform.matrix)
        self.current_fill = style.fill_rgba
        self.direct_fill_allowed = (
            self.current_fill is not None
            and style.stroke_rgba is None
            and not style.erasing
            and style.blend_mode == self.constants.BLEND
        )

    def append_fill_primitive(self, kind: int, coords: tuple[float, ...]) -> bool:
        """Append an eligible fill primitive without crossing renderer batch boundaries."""
        if not self.direct_fill_allowed or self.current_fill is None:
            return False
        if not self.direct_fill_active:
            self.renderer._flush_batches_before_primitive_batch()
            self.primitive_records = self.primitive_batch.records
            self.direct_fill_active = True
        if self.primitive_batch.has_records() and not self.primitive_batch.matches_fill(
            self.matrix_payload
        ):
            self.renderer._flush_primitive_batch_only()
            self.primitive_records = self.primitive_batch.records
        self.primitive_records.append((kind, *coords, *self.current_fill))
        self.primitive_batch.style = None
        self.primitive_batch.matrix = self.matrix_payload
        self.primitive_batch.current = False
        self.primitive_batch.mode = "fill"
        return True


def dispatch_canvas_commands(world: EcsWorld, report: dict[str, Any]) -> None:
    """Replay canvas draw commands emitted by Rust ECS physical execution."""

    commands = report.get("canvas_commands", ())
    if not commands:
        return
    state = _new_canvas_replay_state(world)
    handlers = _canvas_command_handlers(state.context)
    for command in commands:
        name, args = _unpack_canvas_command(command)
        if _append_compact_fill_primitive(state, name, args):
            continue
        _dispatch_canvas_command(state, handlers, name, args)
    world._diagnostics["ecs_canvas_commands"] += len(commands)


def _new_canvas_replay_state(world: EcsWorld) -> _CanvasReplayState:
    context = world.context
    if context is None:
        raise SystemExecutionError("ECS canvas draw commands require an active SketchContext.")
    from gummysnake import constants as c

    renderer = cast(Any, context.renderer)
    return _CanvasReplayState(context, renderer, renderer._primitive_batch_state, c)


def _canvas_command_handlers(context: Any) -> dict[str, Callable[..., Any]]:
    fast = context.fast()
    return {
        **_state_command_handlers(context),
        **_primitive_command_handlers(fast),
        **_text_command_handlers(context, fast),
    }


def _state_command_handlers(context: Any) -> dict[str, Callable[..., Any]]:
    return {
        "background": context.background,
        "clear": context.clear,
        "fill": context.fill,
        "no_fill": context.no_fill,
        "stroke": context.stroke,
        "no_stroke": context.no_stroke,
        "stroke_weight": context.stroke_weight,
    }


def _primitive_command_handlers(fast: Any) -> dict[str, Callable[..., Any]]:
    return {
        "rect": fast.rect,
        "circle": fast.circle,
        "ellipse": fast.ellipse,
        "line": fast.line,
        "triangle": fast.triangle,
    }


def _text_command_handlers(context: Any, fast: Any) -> dict[str, Callable[..., Any]]:
    return {"text_size": context.text_size, "text": fast.text}


def _unpack_canvas_command(command: Any) -> tuple[str, Sequence[Any]]:
    if isinstance(command, (tuple, list)) and len(command) == 2:
        name = str(command[0])
        args = command[1]
    elif isinstance(command, dict):
        name = str(command.get("command", ""))
        args = command.get("args", ())
    else:
        raise SystemExecutionError("Malformed ECS canvas command report.")
    if not name:
        raise SystemExecutionError("Malformed ECS canvas command without a command name.")
    return name, cast(Sequence[Any], args)


def _append_compact_fill_primitive(
    state: _CanvasReplayState, name: str, args: Sequence[Any]
) -> bool:
    from gummysnake.drawing.primitive_fast_path import (
        PRIMITIVE_ELLIPSE,
        PRIMITIVE_RECT,
        PRIMITIVE_TRIANGLE,
    )

    if name == "rect":
        return _append_compact_rect(state, args, PRIMITIVE_RECT)
    if name == "circle":
        return _append_compact_circle(state, args, PRIMITIVE_ELLIPSE)
    if name == "ellipse":
        return _append_compact_ellipse(state, args, PRIMITIVE_ELLIPSE)
    if name == "triangle":
        return _append_compact_triangle(state, args, PRIMITIVE_TRIANGLE)
    return False


def _append_compact_rect(state: _CanvasReplayState, args: Sequence[Any], kind: int) -> bool:
    if len(args) != 4 or state.context.state.style.rect_mode != state.constants.CORNER:
        return False
    return state.append_fill_primitive(kind, (args[0], args[1], args[2], args[3], 0.0, 0.0))


def _append_compact_circle(state: _CanvasReplayState, args: Sequence[Any], kind: int) -> bool:
    if len(args) != 3 or state.context.state.style.ellipse_mode != state.constants.CENTER:
        return False
    diameter = args[2]
    return state.append_fill_primitive(
        kind, (args[0] - diameter / 2.0, args[1] - diameter / 2.0, diameter, diameter, 0.0, 0.0)
    )


def _append_compact_ellipse(state: _CanvasReplayState, args: Sequence[Any], kind: int) -> bool:
    if len(args) not in {3, 4} or state.context.state.style.ellipse_mode != state.constants.CENTER:
        return False
    width = args[2]
    height = width if len(args) == 3 else args[3]
    return state.append_fill_primitive(
        kind, (args[0] - width / 2.0, args[1] - height / 2.0, width, height, 0.0, 0.0)
    )


def _append_compact_triangle(state: _CanvasReplayState, args: Sequence[Any], kind: int) -> bool:
    if len(args) != 6:
        return False
    return state.append_fill_primitive(kind, tuple(args))


def _dispatch_canvas_command(
    state: _CanvasReplayState,
    handlers: dict[str, Callable[..., Any]],
    name: str,
    args: Sequence[Any],
) -> None:
    _resolve_canvas_handler(state.context, handlers, name)(*args)
    if name not in _STYLE_COMMANDS:
        state.direct_fill_active = False
    state.refresh_direct_fill_state()


def _resolve_canvas_handler(
    context: Any, handlers: dict[str, Callable[..., Any]], name: str
) -> Callable[..., Any]:
    handler = handlers.get(name)
    if handler is not None:
        return handler
    candidate = getattr(context, name, None)
    if not callable(candidate):
        raise SystemExecutionError(f"Unsupported ECS canvas command {name!r}.")
    handler = cast(Callable[..., Any], candidate)
    handlers[name] = handler
    return handler


def refresh_rust_input_states(world: EcsWorld, payload: dict[str, Any] | None) -> None:
    """Refresh Rust input-state resources required by a compiled physical plan."""
    if payload is None:
        return
    for expr in payload.get("expressions", ()):  # tiny input binding pass; not ECS execution
        if not isinstance(expr, dict) or expr.get("kind") != "input_state":
            continue
        name = str(expr.get("name", ""))
        code = expr.get("code")
        int_code = int(code) if code is not None else None
        if name == "dt":
            world._rust.set_input_state("dt", _current_delta_time(world))
        elif name == "key_down" and int_code is not None:
            world._rust.set_input_state("key_down", _current_key_down(world, int_code), int_code)


def apply_physical_report(world: EcsWorld, report: dict[str, Any]) -> None:
    """Apply component/resource/event mutations reported by Rust physical execution."""
    previous_defer_spatial = world._defer_spatial_invalidation
    previous_spatial_invalidated = world._spatial_invalidated_deferred
    world._defer_spatial_invalidation = True
    world._spatial_invalidated_deferred = False
    try:
        for write in report.get("component_writes", ()):
            component_type = world._component_type_for_schema(str(write["component"]))
            entity = Entity(int(write["index"]), int(write["generation"]), world._world_id)
            world._mark_component_changed(entity, component_type)
        for event in report.get("events", ()):
            event_type = world._component_type_for_schema(str(event["event_type"]))
            payload = _event_payload_from_bridge(event_type, event["payload"])
            world._events.setdefault(event_type, []).append(
                (world._ecs_frame, copy.deepcopy(payload))
            )
        for write in report.get("resource_writes", ()):
            world._component_type_for_schema(str(write["resource"]))
            world._note_resource_update()
    finally:
        invalidated = world._spatial_invalidated_deferred
        world._defer_spatial_invalidation = previous_defer_spatial
        world._spatial_invalidated_deferred = previous_spatial_invalidated or invalidated
        if invalidated and not previous_defer_spatial:
            world._spatial_invalidated_deferred = previous_spatial_invalidated
            world._invalidate_spatial_indexes()
