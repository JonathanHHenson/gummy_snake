from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

from gummysnake.assets._audio_codec import MemorySoundSource
from gummysnake.assets.sound import Sound
from gummysnake.exceptions import ArgumentValidationError
from gummysnake.synth.synth_runtime.event_api import _resolve_sample_source
from gummysnake.synth.synth_runtime.logical_nodes import ScheduledControl, ScheduledEvent
from gummysnake.synth.synth_runtime.pattern_helpers import note_frequency
from gummysnake.synth.synth_runtime.runtime_foundation import _as_float, _as_int
from gummysnake.synth.synth_runtime.samples_and_export import _wav_duration_seconds
from gummysnake.synth.synth_runtime.scales_and_specs import FxHandle
from gummysnake.synth.synth_runtime.lazy_values import Ring


def _scheduled_event_to_dict(event: ScheduledEvent) -> dict[str, object]:
    return {
        "instance": [_serialize_synth_value(item) for item in event.instance],
        "node_id": event.node_id,
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


def _scheduled_event_from_dict(value: object) -> ScheduledEvent:
    if not isinstance(value, Mapping):
        raise ArgumentValidationError("Serialized synth event must be an object.")
    mapping = cast(Mapping[str, object], value)
    kind = mapping.get("kind", "play")
    if kind not in {"play", "sample"}:
        raise ArgumentValidationError(f"Serialized synth event kind {kind!r} is not supported.")
    fx_value = mapping.get("fx_chain", ())
    if not isinstance(fx_value, Sequence) or isinstance(fx_value, str | bytes):
        raise ArgumentValidationError("Serialized synth event fx_chain must be a list.")
    return ScheduledEvent(
        instance=_deserialize_instance(mapping.get("instance", ())),
        node_id=_as_int(mapping.get("node_id", 0)),
        kind=cast(Literal["play", "sample"], kind),
        time_seconds=_as_float(mapping.get("time_seconds", 0.0)),
        value=_deserialize_plan_value(mapping.get("value")),
        opts=cast(Mapping[str, object], _deserialize_plan_value(mapping.get("opts", {}))),
        synth_name=str(mapping.get("synth_name", "beep")),
        synth_opts=cast(
            Mapping[str, object], _deserialize_plan_value(mapping.get("synth_opts", {}))
        ),
        fx_chain=tuple(_fx_handle_from_dict(item) for item in fx_value),
        order=_as_int(mapping.get("order", 0)),
    )


def _scheduled_control_from_dict(value: object) -> ScheduledControl:
    if not isinstance(value, Mapping):
        raise ArgumentValidationError("Serialized synth control must be an object.")
    mapping = cast(Mapping[str, object], value)
    return ScheduledControl(
        target_instance=_deserialize_instance(mapping.get("target_instance", ())),
        target_id=_as_int(mapping.get("target_id", 0)),
        time_seconds=_as_float(mapping.get("time_seconds", 0.0)),
        opts=cast(Mapping[str, object], _deserialize_plan_value(mapping.get("opts", {}))),
        order=_as_int(mapping.get("order", 0)),
    )


def _fx_handle_from_dict(value: object) -> FxHandle:
    if not isinstance(value, Mapping):
        raise ArgumentValidationError("Serialized synth FX handle must be an object.")
    mapping = cast(Mapping[str, object], value)
    return FxHandle(
        id=_as_int(mapping.get("id", 0)),
        name=str(mapping.get("name", "level")),
        opts=cast(dict[str, object], _deserialize_plan_value(mapping.get("opts", {}))),
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
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze_instance_part(item)) for key, item in value.items()))
    return value


def _deserialize_plan_value(value: object) -> object:
    if isinstance(value, list):
        return [_deserialize_plan_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _deserialize_plan_value(item) for key, item in value.items()}
    return value


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
    return {str(name): _serialize_synth_value(value) for name, value in opts.items()}


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
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Ring | list | tuple):
        return [_serialize_synth_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _serialize_synth_value(item) for key, item in value.items()}
    return str(value)


def _render_event_sound(
    event: ScheduledEvent,
    controls: Sequence[ScheduledControl],
    fx_controls: Mapping[int, Sequence[ScheduledControl]],
    sample_rate: int,
    player_factory: Any | None,
    name: str,
) -> Sound | None:
    from gummysnake.synth.synth_runtime.rendering import _require_synth_runtime

    runtime = _require_synth_runtime()
    payload = bytes(
        runtime.synth_render_event_wav(
            _event_payload(event, controls, fx_controls),
            int(sample_rate),
        )
    )
    if not payload:
        return None
    seconds = _wav_duration_seconds(payload)
    if seconds <= 0:
        return None
    return Sound(
        MemorySoundSource(payload, duration=seconds),
        path=Path(f"{name}-event-{event.node_id}.wav"),
        player_factory=player_factory,
    )


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
