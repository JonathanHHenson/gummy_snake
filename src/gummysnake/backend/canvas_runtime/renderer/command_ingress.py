"""Versioned packed frame-command records for the mandatory Rust canvas runtime."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from struct import Struct
from typing import Protocol, cast

from gummysnake import constants as c

FRAME_COMMAND_ABI_VERSION = 1

PRIMITIVE_STYLE_RECORD = Struct("<BB6x4B4Bd")
MATRIX_RECORD = Struct("<6d")
PATH_POINT_RECORD = Struct("<2d")
PATH_CONTOUR_RECORD = Struct("<I")
IMAGE_RECORD = Struct("<IB3x4d4i6d")
TEXT_RECORD = Struct("<II2d")
MODEL_TRANSFORM_RECORD = Struct("<16d")
EFFECT_RECORD = Struct("<BB6xQQiid")

_BLEND_CODES = {
    c.BLEND: 0,
    c.ADD: 1,
    c.DARKEST: 2,
    c.LIGHTEST: 3,
    c.DIFFERENCE: 4,
    c.EXCLUSION: 5,
    c.MULTIPLY: 6,
    c.REPLACE: 7,
    c.SCREEN: 8,
}
_FILTER_CODES = {
    c.GRAY: 1,
    c.INVERT: 2,
    c.THRESHOLD: 3,
    c.BLUR: 4,
    c.POSTERIZE: 5,
    c.ERODE: 6,
    c.DILATE: 7,
}

MatrixPayload = tuple[float, float, float, float, float, float]
ModelTransformPayload = Sequence[float] | Sequence[Sequence[float]]


class RustImageHandle(Protocol):
    key: int


def pack_matrix(matrix: MatrixPayload) -> bytes:
    """Pack one affine transform using the frame-command ABI."""
    return MATRIX_RECORD.pack(*matrix)


def pack_model_transform(transform: ModelTransformPayload) -> bytes:
    """Normalize one supported model transform into the fixed-width frame-command ABI."""
    values: tuple[float, ...]
    if len(transform) == 4 and all(
        isinstance(row, Sequence) and len(row) == 4 for row in transform
    ):
        rows = cast(Sequence[Sequence[float]], transform)
        values = tuple(float(rows[row][column]) for column in range(4) for row in range(4))
    elif len(transform) in (6, 16) and not any(isinstance(value, Sequence) for value in transform):
        values = tuple(float(value) for value in cast(Sequence[float], transform))
        if len(values) == 6:
            a, b, c, d, e, f = values
            z_scale = max((math.hypot(a, b) + math.hypot(c, d)) / 2.0, 1e-9)
            values = (
                a,
                b,
                0.0,
                0.0,
                c,
                d,
                0.0,
                0.0,
                0.0,
                0.0,
                z_scale,
                0.0,
                e,
                -f,
                0.0,
                1.0,
            )
    else:
        raise ValueError(
            "Batched model transforms must contain 6 affine values, 16 matrix values, "
            "or nested 4x4 rows."
        )
    return MODEL_TRANSFORM_RECORD.pack(*values)


def pack_primitive_style(style: dict[str, object]) -> bytes:
    """Pack primitive-relevant style fields without carrying a Python dictionary into Rust."""
    fill = cast(tuple[int, int, int, int] | None, style.get("fill"))
    stroke = cast(tuple[int, int, int, int] | None, style.get("stroke"))
    flags = (1 if fill is not None else 0) | (2 if stroke is not None else 0)
    if bool(style.get("erasing", False)):
        flags |= 4
    blend_mode = cast(c.BlendMode, style.get("blend_mode", c.BLEND))
    try:
        blend_code = _BLEND_CODES[blend_mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported primitive blend mode {blend_mode!r}.") from exc
    return PRIMITIVE_STYLE_RECORD.pack(
        flags,
        blend_code,
        *(fill or (0, 0, 0, 0)),
        *(stroke or (0, 0, 0, 0)),
        float(cast(float | int, style.get("stroke_weight", 1.0))),
    )


def pack_path(
    outer: list[tuple[float, float]],
    contours: list[list[tuple[float, float]]] | None = None,
) -> tuple[bytes, bytes]:
    """Pack path points and cumulative contour ends."""
    point_payload = bytearray()
    contour_payload = bytearray()
    point_count = 0
    for group in (outer, *(contours or [])):
        for x, y in group:
            point_payload.extend(PATH_POINT_RECORD.pack(float(x), float(y)))
            point_count += 1
        contour_payload.extend(PATH_CONTOUR_RECORD.pack(point_count))
    return bytes(point_payload), bytes(contour_payload)


def pack_adjust_prefix_effect(
    byte_limit: int,
    stride: int,
    red_delta: int,
    green_delta: int,
) -> bytes:
    return EFFECT_RECORD.pack(1, 0, byte_limit, stride, red_delta, green_delta, 0.0)


def pack_filter_effect(mode: c.ImageFilter, value: float | None) -> bytes:
    try:
        mode_code = _FILTER_CODES[mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported image filter {mode!r}.") from exc
    if value is not None:
        mode_code |= 0x80
    return EFFECT_RECORD.pack(2, mode_code, 0, 0, 0, 0, 0.0 if value is None else float(value))


@dataclass(slots=True)
class PackedImageBatchState:
    """Compact image records plus stable Rust image handles for one ordered run."""

    records: bytearray = field(default_factory=bytearray)
    images: list[object] = field(default_factory=list)
    image_indices: dict[int, int] = field(default_factory=dict)
    style: dict[str, object] | None = None
    record_count: int = 0

    def __bool__(self) -> bool:
        return self.record_count > 0

    def append(
        self,
        rust_image: object,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        source: tuple[int, int, int, int] | None,
        matrix: MatrixPayload,
    ) -> None:
        key = int(cast(RustImageHandle, rust_image).key)
        image_index = self.image_indices.get(key)
        if image_index is None:
            image_index = len(self.images)
            self.image_indices[key] = image_index
            self.images.append(rust_image)
        flags = 1 if source is not None else 0
        self.records.extend(
            IMAGE_RECORD.pack(
                image_index,
                flags,
                float(dx),
                float(dy),
                float(dw),
                float(dh),
                *(source or (0, 0, 0, 0)),
                *matrix,
            )
        )
        self.record_count += 1

    def drain(self) -> tuple[bytes, list[object], dict[str, object] | None, int]:
        snapshot = (bytes(self.records), self.images, self.style, self.record_count)
        self.records.clear()
        self.images = []
        self.image_indices.clear()
        self.style = None
        self.record_count = 0
        return snapshot


@dataclass(slots=True)
class PackedTextBatchState:
    """UTF-8 text blob and fixed-width placement records for one style/transform run."""

    records: bytearray = field(default_factory=bytearray)
    utf8: bytearray = field(default_factory=bytearray)
    style: dict[str, object] | None = None
    matrix: MatrixPayload | None = None
    record_count: int = 0

    def __bool__(self) -> bool:
        return self.record_count > 0

    def append(self, value: str, x: float, y: float) -> None:
        encoded = value.encode("utf-8")
        offset = len(self.utf8)
        self.utf8.extend(encoded)
        self.records.extend(TEXT_RECORD.pack(offset, len(encoded), float(x), float(y)))
        self.record_count += 1

    def drain(
        self,
    ) -> tuple[bytes, bytes, dict[str, object] | None, MatrixPayload | None, int]:
        snapshot = (
            bytes(self.records),
            bytes(self.utf8),
            self.style,
            self.matrix,
            self.record_count,
        )
        self.records.clear()
        self.utf8.clear()
        self.style = None
        self.matrix = None
        self.record_count = 0
        return snapshot
