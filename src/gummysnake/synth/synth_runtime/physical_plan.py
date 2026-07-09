# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
@dataclass(frozen=True, slots=True)
class PhysicalPlan:
    """Expanded track ready for deterministic rendering."""

    events: tuple[ScheduledEvent, ...]
    controls: tuple[ScheduledControl, ...]
    duration_seconds: float
    sample_rate: int = _SAMPLE_RATE
    metadata: Mapping[str, object] = field(default_factory=dict)

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
        ).encode("utf-8")
        compressed = zlib.compress(raw, level=9)
        return _GSS_HEADER.pack(_GSS_MAGIC, _GSS_COMPRESSION, len(raw)) + compressed

    def save(self, path: str | Path, *, metadata: Mapping[str, object] | None = None) -> Path:
        """Write this physical plan to a binary plan file and return the path."""

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self.to_bytes(metadata=metadata))
        return output_path

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> PhysicalPlan:
        """Load a physical plan from :meth:`to_dict` output."""

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
        metadata = (
            cast(Mapping[str, object], _deserialize_plan_value(metadata_value))
            if isinstance(metadata_value, Mapping)
            else {}
        )
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
        if len(data) < _GSS_HEADER.size:
            raise ArgumentValidationError("Serialized synth physical plan is too short.")
        magic, compression, raw_size = _GSS_HEADER.unpack(data[: _GSS_HEADER.size])
        if magic != _GSS_MAGIC:
            raise ArgumentValidationError(
                "Serialized synth physical plan has an invalid binary header."
            )
        body = data[_GSS_HEADER.size :]
        if compression == _GSS_COMPRESSION:
            raw = zlib.decompress(body)
        else:
            raise ArgumentValidationError(
                f"Unsupported synth physical-plan compression mode {compression}."
            )
        if len(raw) != raw_size:
            raise ArgumentValidationError("Serialized synth physical plan size check failed.")
        decoded = json.loads(raw.decode("utf-8"))
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

        return _render_physical_plan(
            self, sample_rate=self.sample_rate if sample_rate is None else sample_rate
        )
