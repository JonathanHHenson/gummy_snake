"""Private helper functions for the Python ECS world facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from gummysnake.ecs.actions import Action, DefaultAction, ForEachAction, WhenAction
from gummysnake.ecs.runtime_views import Entity, SystemHandle

if TYPE_CHECKING:  # pragma: no cover
    from gummysnake.ecs.world import EcsWorld


def _handle_matches(handle: SystemHandle, value: SystemHandle | str) -> bool:
    return handle == value if isinstance(value, SystemHandle) else handle.name == value


def _is_direct_udf_action(action: Action) -> bool:
    return isinstance(action, DefaultAction) and action.kind == "udf"


def _is_sequence_action(action: Action) -> bool:
    return isinstance(action, DefaultAction) and action.kind == "sequence"


def _contains_direct_udf_action(action: Action) -> bool:
    if _is_direct_udf_action(action):
        return True
    if isinstance(action, DefaultAction):
        return any(_contains_direct_udf_action(child) for child in action.children)
    if isinstance(action, ForEachAction):
        return _contains_direct_udf_action(action.body)
    if isinstance(action, WhenAction):
        if any(_contains_direct_udf_action(branch) for _, branch in action.branches):
            return True
        return action.otherwise_action is not None and _contains_direct_udf_action(
            action.otherwise_action
        )
    return False


_DIRECT_CANVAS_STYLE_COMMANDS = frozenset(
    {
        "fill",
        "no_fill",
        "stroke",
        "no_stroke",
        "stroke_weight",
        "rect_mode",
        "ellipse_mode",
        "image_mode",
    }
)
_DIRECT_CANVAS_FILL_PRIMITIVE_ARITIES = {
    "rect": {4},
    "circle": {3},
    "ellipse": {3, 4},
    "triangle": {6},
}


def _contains_canvas_action(action: Action) -> bool:
    if isinstance(action, DefaultAction):
        if action.kind == "canvas":
            return True
        return any(_contains_canvas_action(child) for child in action.children)
    if isinstance(action, ForEachAction):
        return _contains_canvas_action(action.body)
    if isinstance(action, WhenAction):
        if any(_contains_canvas_action(branch) for _, branch in action.branches):
            return True
        return action.otherwise_action is not None and _contains_canvas_action(
            action.otherwise_action
        )
    return False


def _is_direct_canvas_barrier_command(action: DefaultAction) -> bool:
    command = action.canvas_command or ""
    if command in _DIRECT_CANVAS_STYLE_COMMANDS:
        return False
    arities = _DIRECT_CANVAS_FILL_PRIMITIVE_ARITIES.get(command)
    return arities is None or len(action.canvas_args) not in arities


def _contains_direct_canvas_barrier_action(action: Action) -> bool:
    """Return whether direct canvas replay cannot preserve this action's draw order.

    The Rust direct replay path can consume style commands and supported fill
    primitive commands internally. Commands such as ``background`` and ``text``
    must be replayed by Python in schedule order; rendering later direct fills
    before those commands would let the retained command cover or reorder them.
    """

    if isinstance(action, DefaultAction):
        if action.kind == "canvas":
            return _is_direct_canvas_barrier_command(action)
        return any(_contains_direct_canvas_barrier_action(child) for child in action.children)
    if isinstance(action, ForEachAction):
        return _contains_direct_canvas_barrier_action(action.body)
    if isinstance(action, WhenAction):
        if any(_contains_direct_canvas_barrier_action(branch) for _, branch in action.branches):
            return True
        return action.otherwise_action is not None and _contains_direct_canvas_barrier_action(
            action.otherwise_action
        )
    return False


def _component_key(entity: Entity, component_type: type[Any]) -> tuple[int, int, type[Any]]:
    return (entity.index, entity.generation, component_type)


def _payload_has_input_state(payload: dict[str, Any]) -> bool:
    return any(
        isinstance(expr, dict) and expr.get("kind") == "input_state"
        for expr in payload.get("expressions", ())
    )


def _optional_rust_int(rust_world: object, method_name: str) -> int:
    method = getattr(rust_world, method_name, None)
    if not callable(method):
        return 0
    return int(cast(Any, method()))


def _current_delta_time(world: EcsWorld) -> float:
    context = getattr(world, "context", None)
    if context is None:
        return 0.0
    return float(getattr(context, "delta_time", 0.0))


def _current_key_down(world: EcsWorld, key: int) -> bool:
    context = getattr(world, "context", None)
    if context is None:
        return False
    key_is_down = getattr(context, "key_is_down", None)
    if not callable(key_is_down):
        return False
    return bool(key_is_down(key))
