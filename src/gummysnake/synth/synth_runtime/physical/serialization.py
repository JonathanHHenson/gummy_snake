from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

from gummysnake.exceptions import ArgumentValidationError
from gummysnake.synth.synth_runtime.composition.event_api import _resolve_sample_source
from gummysnake.synth.synth_runtime.composition.logical_nodes import (
    ScheduledControl,
    ScheduledEvent,
)
from gummysnake.synth.synth_runtime.physical.physical_plan import PhysicalPlan
from gummysnake.synth.synth_runtime.values.foundation import (
    _MAX_FX_CHAIN_DEPTH,
    _MAX_PLAN_VALUE_DEPTH,
    _MAX_PLAN_VALUE_ITEMS,
    Expression,
    _as_float,
    _as_int,
)
from gummysnake.synth.synth_runtime.values.lazy_values import Ring
from gummysnake.synth.synth_runtime.values.scales_and_specs import FxHandle


def _scheduled_event_to_dict(event: ScheduledEvent) -> dict[str, object]:
    return {
        "instance": [_serialize_synth_value(item) for item in event.instance],
        "node_id": event.node_id,
        "seed": event.seed,
        "kind": event.kind,
        "time_seconds": event.time_seconds,
        "value": _serialize_synth_value(event.value),
        "opts": _serialize_opts(event.opts),
        "synth_name": event.synth_name,
        "synth_opts": _serialize_opts(event.synth_opts),
        "fx_chain": [
            {"id": fx.id, "name": fx.name, "opts": _serialize_opts(fx.opts)}
            for fx in event.fx_chain
        ],
        "order": event.order,
    }


def _scheduled_control_to_dict(control: ScheduledControl) -> dict[str, object]:
    return {
        "target_instance": [_serialize_synth_value(item) for item in control.target_instance],
        "target_id": control.target_id,
        "time_seconds": control.time_seconds,
        "opts": _serialize_opts(control.opts),
        "order": control.order,
    }


def _scheduled_event_from_dict(value: object, *, allow_expressions: bool = False) -> ScheduledEvent:
    if not isinstance(value, Mapping):
        raise ArgumentValidationError("Serialized synth event must be an object.")
    mapping = cast(Mapping[str, object], value)
    _validate_mapping_keys(
        mapping,
        {
            "instance",
            "node_id",
            "seed",
            "kind",
            "time_seconds",
            "value",
            "opts",
            "synth_name",
            "synth_opts",
            "fx_chain",
            "order",
        },
        "Serialized synth event",
    )
    kind = mapping.get("kind", "play")
    if kind not in {"play", "sample"}:
        raise ArgumentValidationError(f"Serialized synth event kind {kind!r} is not supported.")
    fx_value = mapping.get("fx_chain", ())
    if not isinstance(fx_value, Sequence) or isinstance(fx_value, str | bytes):
        raise ArgumentValidationError("Serialized synth event fx_chain must be a list.")
    if len(fx_value) > _MAX_FX_CHAIN_DEPTH:
        raise ArgumentValidationError(
            f"Serialized synth event fx_chain exceeds the maximum depth of {_MAX_FX_CHAIN_DEPTH}."
        )
    return ScheduledEvent(
        instance=_deserialize_instance(mapping.get("instance", ())),
        node_id=_as_int(mapping.get("node_id", 0)),
        seed=_as_int(mapping.get("seed", 0)),
        kind=cast(Literal["play", "sample"], kind),
        time_seconds=_as_float(mapping.get("time_seconds", 0.0)),
        value=_deserialize_plan_value(mapping.get("value"), allow_expressions=allow_expressions),
        opts=cast(
            Mapping[str, object],
            _deserialize_plan_value(mapping.get("opts", {}), allow_expressions=allow_expressions),
        ),
        synth_name=_required_string(mapping.get("synth_name", "beep"), "synth_name"),
        synth_opts=cast(
            Mapping[str, object],
            _deserialize_plan_value(
                mapping.get("synth_opts", {}), allow_expressions=allow_expressions
            ),
        ),
        fx_chain=tuple(
            _fx_handle_from_dict(item, allow_expressions=allow_expressions) for item in fx_value
        ),
        order=_as_int(mapping.get("order", 0)),
    )


def _scheduled_control_from_dict(
    value: object, *, allow_expressions: bool = False
) -> ScheduledControl:
    if not isinstance(value, Mapping):
        raise ArgumentValidationError("Serialized synth control must be an object.")
    mapping = cast(Mapping[str, object], value)
    _validate_mapping_keys(
        mapping,
        {"target_instance", "target_id", "time_seconds", "opts", "order"},
        "Serialized synth control",
    )
    return ScheduledControl(
        target_instance=_deserialize_instance(mapping.get("target_instance", ())),
        target_id=_as_int(mapping.get("target_id", 0)),
        time_seconds=_as_float(mapping.get("time_seconds", 0.0)),
        opts=cast(
            Mapping[str, object],
            _deserialize_plan_value(mapping.get("opts", {}), allow_expressions=allow_expressions),
        ),
        order=_as_int(mapping.get("order", 0)),
    )


def _fx_handle_from_dict(value: object, *, allow_expressions: bool = False) -> FxHandle:
    if not isinstance(value, Mapping):
        raise ArgumentValidationError("Serialized synth FX handle must be an object.")
    mapping = cast(Mapping[str, object], value)
    _validate_mapping_keys(mapping, {"id", "name", "opts"}, "Serialized synth FX handle")
    return FxHandle(
        id=_as_int(mapping.get("id", 0)),
        name=_required_string(mapping.get("name", "level"), "FX name"),
        opts=cast(
            dict[str, object],
            _deserialize_plan_value(mapping.get("opts", {}), allow_expressions=allow_expressions),
        ),
    )


def _deserialize_instance(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(_freeze_instance_part(item) for item in value)
    return (_freeze_instance_part(value),)


def _freeze_instance_part(value: object) -> object:
    if isinstance(value, list | tuple):
        return tuple(_freeze_instance_part(item) for item in value)
    if isinstance(value, Mapping):
        raise ArgumentValidationError(
            "Serialized synth instance identities do not support mappings."
        )
    if value is None or isinstance(value, bool | int | str):
        return value
    raise ArgumentValidationError(
        "Serialized synth instance identities support only None, bool, integer, "
        "string, and nested lists."
    )


def _deserialize_plan_value(value: object, *, allow_expressions: bool = False) -> object:
    item_count = [0]
    return _deserialize_plan_value_at_depth(
        value,
        depth=0,
        item_count=item_count,
        allow_expressions=allow_expressions,
    )


def _deserialize_plan_value_at_depth(
    value: object,
    *,
    depth: int,
    item_count: list[int],
    allow_expressions: bool,
) -> object:
    _consume_value_budget(depth, item_count)
    if allow_expressions and isinstance(value, Expression):
        return value
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        if abs(value) > 2**53:
            raise ArgumentValidationError(
                "Serialized synth integer values must be exactly representable as f64."
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ArgumentValidationError("Serialized synth numeric values must be finite.")
        return value
    if isinstance(value, list | tuple):
        return [
            _deserialize_plan_value_at_depth(
                item,
                depth=depth + 1,
                item_count=item_count,
                allow_expressions=allow_expressions,
            )
            for item in value
        ]
    if isinstance(value, Mapping):
        output: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ArgumentValidationError(
                    "Serialized synth mapping keys must be strings; keys are not coerced."
                )
            if not key:
                raise ArgumentValidationError("Serialized synth mapping keys cannot be empty.")
            output[key] = _deserialize_plan_value_at_depth(
                item,
                depth=depth + 1,
                item_count=item_count,
                allow_expressions=allow_expressions,
            )
        return output
    raise ArgumentValidationError(
        "Serialized synth values must be None, bool, finite number, string, list, tuple, "
        "or string-keyed mapping."
    )


def _control_lookup(
    plan: PhysicalPlan,
) -> tuple[
    dict[tuple[object, ...], list[ScheduledControl]],
    dict[int, list[ScheduledControl]],
]:
    controls_by_instance: dict[tuple[object, ...], list[ScheduledControl]] = {}
    fx_controls: dict[int, list[ScheduledControl]] = {}
    for control_node in sorted(plan.controls, key=lambda item: (item.time_seconds, item.order)):
        controls_by_instance.setdefault(control_node.target_instance, []).append(control_node)
        fx_controls.setdefault(control_node.target_id, []).append(control_node)
    return controls_by_instance, fx_controls


def _event_payload(
    event: ScheduledEvent,
    controls: Sequence[ScheduledControl],
    fx_controls: Mapping[int, Sequence[ScheduledControl]],
) -> dict[str, object]:
    return {
        "node_id": event.node_id,
        "seed": event.seed,
        "order": event.order,
        "kind": event.kind,
        "time_seconds": event.time_seconds,
        "value": _serialize_event_value(event),
        "opts": _serialize_opts(event.opts),
        "synth_name": event.synth_name,
        "synth_opts": _serialize_opts(event.synth_opts),
        "fx_chain": [
            {
                "id": fx.id,
                "name": fx.name,
                "opts": _serialize_opts(
                    {
                        **fx.opts,
                        **_fx_opts_at(
                            fx,
                            event.time_seconds,
                            event.order,
                            fx_controls.get(fx.id, ()),
                        ),
                    }
                ),
            }
            for fx in event.fx_chain
        ],
        "controls": [
            {
                "time_seconds": control_node.time_seconds,
                "opts": _serialize_opts(control_node.opts),
            }
            for control_node in controls
        ],
    }


def _serialize_opts(opts: Mapping[str, object]) -> dict[str, object]:
    output: dict[str, object] = {}
    for name, value in opts.items():
        if not isinstance(name, str):
            raise ArgumentValidationError(
                "Synth option keys must be strings; keys are not coerced."
            )
        if not name:
            raise ArgumentValidationError("Synth option keys cannot be empty.")
        output[name] = _serialize_synth_value(value)
    return output


def _serialize_event_value(event: ScheduledEvent) -> object:
    if event.kind != "sample":
        return _serialize_synth_value(event.value)
    return _serialize_sample_value(event.value)


def _serialize_sample_value(value: object) -> object:
    if isinstance(value, Ring | list | tuple):
        values = list(value)
        if not values:
            return []
        return [_serialize_synth_value(_resolve_sample_source(values[0]))] + [
            _serialize_synth_value(item) for item in values[1:]
        ]
    return _serialize_synth_value(_resolve_sample_source(value))


def _serialize_synth_value(value: object) -> object:
    item_count = [0]
    return _serialize_synth_value_at_depth(value, depth=0, item_count=item_count)


def _serialize_synth_value_at_depth(value: object, *, depth: int, item_count: list[int]) -> object:
    _consume_value_budget(depth, item_count)
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        if abs(value) > 2**53:
            raise ArgumentValidationError(
                "Synth integer values must be exactly representable as f64."
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ArgumentValidationError("Synth numeric values must be finite.")
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Ring | list | tuple):
        return [
            _serialize_synth_value_at_depth(item, depth=depth + 1, item_count=item_count)
            for item in value
        ]
    if isinstance(value, Mapping):
        output: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ArgumentValidationError(
                    "Synth mapping keys must be strings; keys are not coerced."
                )
            if not key:
                raise ArgumentValidationError("Synth mapping keys cannot be empty.")
            output[key] = _serialize_synth_value_at_depth(
                item, depth=depth + 1, item_count=item_count
            )
        return output
    raise ArgumentValidationError(
        "Synth values must be None, bool, finite number, string, Path, list, tuple, Ring, "
        "or string-keyed mapping."
    )


def _consume_value_budget(depth: int, item_count: list[int]) -> None:
    if depth > _MAX_PLAN_VALUE_DEPTH:
        raise ArgumentValidationError(
            f"Synth value nesting exceeds the limit of {_MAX_PLAN_VALUE_DEPTH}."
        )
    item_count[0] += 1
    if item_count[0] > _MAX_PLAN_VALUE_ITEMS:
        raise ArgumentValidationError(
            f"Synth value item count exceeds the limit of {_MAX_PLAN_VALUE_ITEMS}."
        )


def _validate_mapping_keys(mapping: Mapping[Any, object], allowed: set[str], label: str) -> None:
    non_string = [key for key in mapping if not isinstance(key, str)]
    if non_string:
        raise ArgumentValidationError(f"{label} keys must be strings; keys are not coerced.")
    unexpected = sorted(key for key in mapping if isinstance(key, str) and key not in allowed)
    if unexpected:
        raise ArgumentValidationError(
            f"{label} contains unsupported key(s): {', '.join(unexpected)}."
        )


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ArgumentValidationError(f"Serialized synth {label} must be a non-empty string.")
    return value


def _fx_opts_at(
    handle: FxHandle,
    event_time: float,
    event_order: int,
    controls: Sequence[ScheduledControl],
) -> dict[str, object]:
    opts = dict(handle.opts)
    for control_node in controls:
        before_event = control_node.time_seconds < event_time - 1e-9
        same_time_before_event = (
            abs(control_node.time_seconds - event_time) <= 1e-9 and control_node.order < event_order
        )
        if before_event or same_time_before_event:
            opts.update(control_node.opts)
    return opts
