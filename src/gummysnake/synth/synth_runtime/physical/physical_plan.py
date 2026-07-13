from __future__ import annotations

import json
import math
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from gummysnake.exceptions import ArgumentValidationError
from gummysnake.synth.synth_runtime.composition.logical_nodes import (
    ScheduledControl,
    ScheduledEvent,
)
from gummysnake.synth.synth_runtime.values.foundation import (
    _GSS_COMPRESSION,
    _GSS_HEADER,
    _GSS_MAGIC,
    _MAX_DECOMPRESSED_PLAN_BYTES,
    _MAX_FX_CHAIN_DEPTH,
    _MAX_OUTPUT_FRAMES,
    _MAX_PLAN_CONTROLS,
    _MAX_PLAN_EVENTS,
    _MAX_SAMPLE_RATE,
    _MAX_SERIALIZED_PLAN_BYTES,
    _PHYSICAL_PLAN_SCHEMA,
    _SAMPLE_RATE,
    _as_float,
    _as_int,
)


@dataclass(frozen=True, slots=True)
class PhysicalPlan:
    """Expanded track ready for deterministic rendering."""

    events: tuple[ScheduledEvent, ...]
    controls: tuple[ScheduledControl, ...]
    duration_seconds: float
    sample_rate: int = _SAMPLE_RATE
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.sample_rate, bool) or not isinstance(self.sample_rate, int):
            raise ArgumentValidationError("Synth physical-plan sample_rate must be an integer.")
        if not 1 <= self.sample_rate <= _MAX_SAMPLE_RATE:
            raise ArgumentValidationError(
                f"Synth physical-plan sample_rate must be in [1, {_MAX_SAMPLE_RATE}]."
            )
        _validate_seconds(self.duration_seconds, "duration_seconds")
        frames = math.ceil(self.duration_seconds * self.sample_rate)
        if frames > _MAX_OUTPUT_FRAMES:
            raise ArgumentValidationError(
                "Synth physical-plan duration exceeds the output budget of "
                f"{_MAX_OUTPUT_FRAMES} frames."
            )
        if len(self.events) > _MAX_PLAN_EVENTS:
            raise ArgumentValidationError(
                f"Synth physical-plan event count exceeds the limit of {_MAX_PLAN_EVENTS}."
            )
        if len(self.controls) > _MAX_PLAN_CONTROLS:
            raise ArgumentValidationError(
                f"Synth physical-plan control count exceeds the limit of {_MAX_PLAN_CONTROLS}."
            )
        from gummysnake.synth.synth_runtime.physical.serialization import (
            _serialize_opts,
            _serialize_synth_value,
        )

        for event in self.events:
            _validate_seconds(event.time_seconds, "event time_seconds")
            if event.time_seconds > self.duration_seconds:
                raise ArgumentValidationError(
                    "Synth event time_seconds cannot exceed the physical-plan duration."
                )
            if event.seed < 0 or event.seed > (1 << 64) - 1:
                raise ArgumentValidationError(
                    "Synth event seed must fit an unsigned 64-bit integer."
                )
            if len(event.fx_chain) > _MAX_FX_CHAIN_DEPTH:
                raise ArgumentValidationError(
                    f"Synth event FX chain exceeds the limit of {_MAX_FX_CHAIN_DEPTH}."
                )
            _serialize_synth_value(event.value)
            _serialize_opts(event.opts)
            _serialize_opts(event.synth_opts)
            for fx in event.fx_chain:
                if not isinstance(fx.name, str) or not fx.name:
                    raise ArgumentValidationError("Synth FX names must be non-empty strings.")
                _serialize_opts(fx.opts)
        for control in self.controls:
            _validate_seconds(control.time_seconds, "control time_seconds")
            _serialize_opts(control.opts)
        _serialize_synth_value(self.metadata)

    def explain(self) -> str:
        """Return a compact physical-plan summary."""

        return (
            f"PhysicalPlan(events={len(self.events)}, controls={len(self.controls)}, "
            f"duration_seconds={self.duration_seconds:.3f}, sample_rate={self.sample_rate})"
        )

    def to_dict(self, *, metadata: Mapping[str, object] | None = None) -> dict[str, object]:
        """Serialize this physical plan to a JSON-compatible dictionary.

        The format stores concrete scheduled events and controls, not lazy
        expressions. It is therefore suitable for compiled synth assets and can be
        loaded back with :meth:`from_dict` without executing the original Python
        source track.
        """

        from gummysnake.synth.synth_runtime.physical.serialization import (
            _scheduled_control_to_dict,
            _scheduled_event_to_dict,
            _serialize_synth_value,
        )

        payload: dict[str, object] = {
            "schema": _PHYSICAL_PLAN_SCHEMA,
            "duration_seconds": self.duration_seconds,
            "sample_rate": self.sample_rate,
            "events": [_scheduled_event_to_dict(event) for event in self.events],
            "controls": [_scheduled_control_to_dict(control) for control in self.controls],
        }
        merged_metadata = dict(self.metadata)
        if metadata is not None:
            merged_metadata.update(dict(metadata))
        if merged_metadata:
            payload["metadata"] = _serialize_synth_value(merged_metadata)
        return payload

    def to_bytes(self, *, metadata: Mapping[str, object] | None = None) -> bytes:
        """Serialize this physical plan to the binary Gummy Snake Synth container."""

        raw = json.dumps(
            self.to_dict(metadata=metadata),
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        if len(raw) > _MAX_DECOMPRESSED_PLAN_BYTES:
            raise ArgumentValidationError(
                "Serialized synth physical plan exceeds the decompressed payload limit of "
                f"{_MAX_DECOMPRESSED_PLAN_BYTES} bytes."
            )
        compressed = zlib.compress(raw, level=9)
        payload = _GSS_HEADER.pack(_GSS_MAGIC, _GSS_COMPRESSION, len(raw)) + compressed
        if len(payload) > _MAX_SERIALIZED_PLAN_BYTES:
            raise ArgumentValidationError(
                "Serialized synth physical plan exceeds the compressed payload limit of "
                f"{_MAX_SERIALIZED_PLAN_BYTES} bytes."
            )
        return payload

    def save(self, path: str | Path, *, metadata: Mapping[str, object] | None = None) -> Path:
        """Write this physical plan to a binary plan file and return the path."""

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self.to_bytes(metadata=metadata))
        return output_path

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> PhysicalPlan:
        """Load a physical plan from :meth:`to_dict` output."""

        if any(not isinstance(key, str) for key in payload):
            raise ArgumentValidationError(
                "Serialized synth physical-plan keys must be strings; keys are not coerced."
            )
        unexpected = sorted(
            key
            for key in payload
            if key
            not in {"schema", "duration_seconds", "sample_rate", "events", "controls", "metadata"}
        )
        if unexpected:
            raise ArgumentValidationError(
                "Serialized synth physical plan contains unsupported key(s): "
                f"{', '.join(unexpected)}."
            )
        schema = payload.get("schema")
        if schema != _PHYSICAL_PLAN_SCHEMA:
            raise ArgumentValidationError(
                "Unsupported synth physical-plan schema "
                f"{schema!r}; expected {_PHYSICAL_PLAN_SCHEMA!r}."
            )
        events_value = payload.get("events", ())
        controls_value = payload.get("controls", ())
        if not isinstance(events_value, Sequence) or isinstance(events_value, str | bytes):
            raise ArgumentValidationError("Serialized synth physical plan events must be a list.")
        if not isinstance(controls_value, Sequence) or isinstance(controls_value, str | bytes):
            raise ArgumentValidationError("Serialized synth physical plan controls must be a list.")
        metadata_value = payload.get("metadata", {})
        from gummysnake.synth.synth_runtime.physical.serialization import (
            _deserialize_plan_value,
            _scheduled_control_from_dict,
            _scheduled_event_from_dict,
        )

        if not isinstance(metadata_value, Mapping):
            raise ArgumentValidationError(
                "Serialized synth physical plan metadata must be an object."
            )
        metadata = cast(Mapping[str, object], _deserialize_plan_value(metadata_value))
        return cls(
            tuple(_scheduled_event_from_dict(event) for event in events_value),
            tuple(_scheduled_control_from_dict(control) for control in controls_value),
            _as_float(payload.get("duration_seconds", 0.0)),
            _as_int(payload.get("sample_rate", _SAMPLE_RATE)),
            metadata,
        )

    @classmethod
    def from_bytes(cls, payload: bytes | bytearray | memoryview) -> PhysicalPlan:
        """Load a physical plan from binary plan bytes."""

        data = bytes(payload)
        if len(data) > _MAX_SERIALIZED_PLAN_BYTES:
            raise ArgumentValidationError(
                "Serialized synth physical plan exceeds the compressed payload limit of "
                f"{_MAX_SERIALIZED_PLAN_BYTES} bytes."
            )
        if len(data) < _GSS_HEADER.size:
            raise ArgumentValidationError("Serialized synth physical plan is too short.")
        magic, compression, raw_size = _GSS_HEADER.unpack(data[: _GSS_HEADER.size])
        if magic != _GSS_MAGIC:
            raise ArgumentValidationError(
                "Serialized synth physical plan has an invalid binary header."
            )
        if raw_size > _MAX_DECOMPRESSED_PLAN_BYTES:
            raise ArgumentValidationError(
                "Serialized synth physical plan declares a decompressed payload larger than "
                f"the {_MAX_DECOMPRESSED_PLAN_BYTES}-byte limit."
            )
        body = data[_GSS_HEADER.size :]
        if compression == _GSS_COMPRESSION:
            decoder = zlib.decompressobj()
            try:
                raw = decoder.decompress(body, _MAX_DECOMPRESSED_PLAN_BYTES + 1)
            except zlib.error as error:
                raise ArgumentValidationError(
                    f"Could not decompress serialized synth physical plan: {error}"
                ) from error
            if len(raw) > _MAX_DECOMPRESSED_PLAN_BYTES or decoder.unconsumed_tail:
                raise ArgumentValidationError(
                    "Serialized synth physical plan decompressed payload exceeds the limit of "
                    f"{_MAX_DECOMPRESSED_PLAN_BYTES} bytes."
                )
            if not decoder.eof:
                raise ArgumentValidationError(
                    "Serialized synth physical plan contains a truncated zlib payload."
                )
            if decoder.unused_data:
                raise ArgumentValidationError(
                    "Serialized synth physical plan contains trailing compressed data."
                )
        else:
            raise ArgumentValidationError(
                f"Unsupported synth physical-plan compression mode {compression}."
            )
        if len(raw) != raw_size:
            raise ArgumentValidationError("Serialized synth physical plan size check failed.")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ArgumentValidationError(
                f"Serialized synth physical plan JSON is invalid: {error}"
            ) from error
        if not isinstance(decoded, Mapping):
            raise ArgumentValidationError(
                "Serialized synth physical plan payload must contain an object."
            )
        return cls.from_dict(cast(Mapping[str, object], decoded))

    @classmethod
    def load(cls, path: str | Path) -> PhysicalPlan:
        """Load a physical plan from a binary plan file."""

        return cls.from_bytes(Path(path).read_bytes())

    def render(self, *, sample_rate: int | None = None) -> bytes:
        """Render this already-expanded plan to stereo 16-bit PCM WAV bytes."""

        from gummysnake.synth.synth_runtime.physical.rendering import _render_physical_plan

        return _render_physical_plan(
            self, sample_rate=self.sample_rate if sample_rate is None else sample_rate
        )


def _validate_seconds(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ArgumentValidationError(f"Synth physical-plan {label} must be numeric.")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ArgumentValidationError(
            f"Synth physical-plan {label} must be finite and non-negative."
        )
