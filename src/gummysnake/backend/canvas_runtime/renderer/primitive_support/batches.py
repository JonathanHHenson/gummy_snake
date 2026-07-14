"""Direct packed primitive ingress for the Rust-owned frame recorder."""

from __future__ import annotations

from collections.abc import Sequence
from struct import Struct
from typing import cast

from gummysnake import constants as c
from gummysnake.backend.canvas_runtime.renderer._protocols import CanvasRendererHost
from gummysnake.backend.canvas_runtime.renderer.command_ingress import (
    pack_matrix,
    pack_primitive_style,
)
from gummysnake.core.state import StyleState
from gummysnake.core.transform import Matrix2D

_PRIMITIVE_RECT = 1
_PRIMITIVE_TRIANGLE = 2
_PRIMITIVE_ELLIPSE = 3
_PRIMITIVE_LINE = 4
_PACKED_LINE_RECORD = Struct("<4d")
_PACKED_PRIMITIVE_RECORD = Struct("<B7x6d")
_PACKED_FILL_PRIMITIVE_RECORD = Struct("<B7x6d4B")
_PACKED_MIXED_PRIMITIVE_RECORD = Struct("<B7x6dII")
_FillPrimitiveRecord = tuple[int, float, float, float, float, float, float, int, int, int, int]


def _pack_primitive_records(
    records: list[tuple[int, float, float, float, float, float, float]],
) -> bytes:
    payload = bytearray(_PACKED_PRIMITIVE_RECORD.size * len(records))
    for index, record in enumerate(records):
        kind, a, b, c1, d, e, f = record
        _PACKED_PRIMITIVE_RECORD.pack_into(
            payload,
            index * _PACKED_PRIMITIVE_RECORD.size,
            int(kind),
            float(a),
            float(b),
            float(c1),
            float(d),
            float(e),
            float(f),
        )
    return bytes(payload)


def _pack_fill_primitive_records(records: list[_FillPrimitiveRecord]) -> bytes:
    payload = bytearray(_PACKED_FILL_PRIMITIVE_RECORD.size * len(records))
    for index, record in enumerate(records):
        kind, a, b, c1, d, e, f, red, green, blue, alpha = record
        _PACKED_FILL_PRIMITIVE_RECORD.pack_into(
            payload,
            index * _PACKED_FILL_PRIMITIVE_RECORD.size,
            int(kind),
            float(a),
            float(b),
            float(c1),
            float(d),
            float(e),
            float(f),
            int(red),
            int(green),
            int(blue),
            int(alpha),
        )
    return bytes(payload)


def _pack_mixed_primitive_records(
    records: list[tuple[object, ...]],
) -> tuple[bytes, bytes, bytes]:
    payload = bytearray(_PACKED_MIXED_PRIMITIVE_RECORD.size * len(records))
    styles = bytearray()
    style_indexes: dict[tuple[object, ...], int] = {}
    matrices = bytearray()
    matrix_indexes: dict[tuple[float, float, float, float, float, float], int] = {}
    for index, (kind, a, b, c1, d, e, f, style, matrix) in enumerate(records):
        typed_style = cast(dict[str, object], style)
        typed_matrix = cast(tuple[float, float, float, float, float, float], matrix)
        style_key = (
            typed_style.get("fill"),
            typed_style.get("stroke"),
            typed_style.get("stroke_weight"),
            typed_style.get("blend_mode"),
            typed_style.get("erasing"),
        )
        style_index = style_indexes.get(style_key)
        if style_index is None:
            style_index = len(style_indexes)
            style_indexes[style_key] = style_index
            styles.extend(pack_primitive_style(typed_style))
        matrix_index = matrix_indexes.get(typed_matrix)
        if matrix_index is None:
            matrix_index = len(matrix_indexes)
            matrix_indexes[typed_matrix] = matrix_index
            matrices.extend(pack_matrix(typed_matrix))
        _PACKED_MIXED_PRIMITIVE_RECORD.pack_into(
            payload,
            index * _PACKED_MIXED_PRIMITIVE_RECORD.size,
            int(cast(int, kind)),
            *cast(tuple[float, float, float, float, float, float], (a, b, c1, d, e, f)),
            style_index,
            matrix_index,
        )
    return bytes(payload), bytes(styles), bytes(matrices)


def _record_submission(renderer: CanvasRendererHost, record_count: int) -> None:
    renderer._count("gpu_draws", record_count)
    renderer._count("primitive_batch_records", record_count)
    renderer._count("primitive_batch_flushes")
    renderer._max_count("primitive_batch_max_records", record_count)


def flush_line_batch(self: CanvasRendererHost) -> None:
    """Flush the pending model run before an ordered non-batched command."""
    if self._model_batch_state.record_count:
        self._flush_model_batch()


def queue_fill_primitive_fast_path(
    self: CanvasRendererHost,
    kind: int,
    coords: tuple[float, ...],
    style: StyleState,
    transform: Matrix2D,
) -> bool:
    if self._model_batch_state.record_count:
        self._flush_model_batch()
    fill_color = style.fill_rgba
    canvas = self._require_canvas()
    batch_fill = getattr(canvas, "batch_fill_primitives_packed", None)
    if (
        kind == _PRIMITIVE_LINE
        or fill_color is None
        or style.stroke_rgba is not None
        or style.erasing
        or style.blend_mode != c.BLEND
        or not callable(batch_fill)
    ):
        return False
    record = cast(_FillPrimitiveRecord, (kind, *coords, *fill_color))
    _record_submission(self, 1)
    self._call(
        "packed fill primitive recording",
        batch_fill,
        _pack_fill_primitive_records([record]),
        self._matrix_payload(transform),
    )
    return True


def record_fill_primitive_batch(
    self: CanvasRendererHost,
    records: Sequence[tuple[object, ...]],
    transform: Matrix2D,
) -> None:
    """Record one Rust-produced compact fill batch without Python queue state."""

    if not records:
        return
    if self._model_batch_state.record_count:
        self._flush_model_batch()
    batch_fill = self._require_canvas_method(
        "batch_fill_primitives_packed",
        "packed fill primitive batch recording",
    )
    typed_records = [cast(_FillPrimitiveRecord, tuple(record)) for record in records]
    _record_submission(self, len(typed_records))
    self._call(
        "packed fill primitive batch recording",
        batch_fill,
        _pack_fill_primitive_records(typed_records),
        self._matrix_payload(transform),
    )


def queue_primitive_batch(
    self: CanvasRendererHost,
    kind: int,
    coords: tuple[float, float, float, float, float, float],
    style: StyleState,
    transform: Matrix2D,
) -> bool:
    if queue_fill_primitive_fast_path(self, kind, coords, style, transform):
        return True
    canvas = self._require_canvas()
    matrix_payload = self._matrix_payload(transform)
    mixed = getattr(canvas, "batch_primitives_mixed_packed", None)
    if callable(mixed):
        payload, styles, matrices = _pack_mixed_primitive_records(
            [(kind, *coords, self._style_payload(style), matrix_payload)]
        )
        _record_submission(self, 1)
        self._call("packed mixed primitive recording", mixed, payload, styles, matrices)
        return True
    current = (
        getattr(canvas, "batch_primitives_current_packed", None)
        if self._can_use_current_state(style, transform)
        else None
    )
    if callable(current):
        _record_submission(self, 1)
        self._call(
            "packed current-state primitive recording",
            current,
            _pack_primitive_records([(kind, *coords)]),
        )
        return True
    styled = self._require_canvas_method(
        "batch_primitives_packed",
        "typed primitive command recording",
    )
    _record_submission(self, 1)
    self._call(
        "packed primitive recording",
        styled,
        _pack_primitive_records([(kind, *coords)]),
        self._style_payload(style),
        matrix_payload,
    )
    return True


def flush_batches_before_primitive_batch(self: CanvasRendererHost) -> None:
    """Flush the pending model run before direct primitive recording."""
    if self._model_batch_state.record_count:
        self._flush_model_batch()


def flush_line_batch_only(self: CanvasRendererHost) -> None:
    """Compatibility no-op; no Python line queue exists."""


def flush_primitive_batch_only(self: CanvasRendererHost) -> None:
    """Compatibility no-op; no Python primitive queue exists."""
