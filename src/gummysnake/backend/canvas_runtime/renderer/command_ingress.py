"""Versioned packed frame-command records for the mandatory Rust canvas runtime."""

from __future__ import annotations

import math
from collections.abc import Sequence
from struct import Struct
from struct import error as StructError
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
MODEL_TRANSLATION_QUATERNION_RECORD = Struct("<7d")
_EMPTY_MODEL_TRANSFORM_RECORD = bytes(MODEL_TRANSFORM_RECORD.size)
_EMPTY_MODEL_TRANSLATION_QUATERNION_RECORD = bytes(MODEL_TRANSLATION_QUATERNION_RECORD.size)
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
    if len(transform) == 16:
        try:
            return MODEL_TRANSFORM_RECORD.pack(*transform)
        except (StructError, TypeError):
            pass

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


def append_model_transform(
    payload: bytearray,
    transform: ModelTransformPayload,
    *,
    offset: int | None = None,
) -> int:
    """Write one model transform, reusing retained payload storage when available."""
    write_offset = len(payload) if offset is None else offset
    if len(transform) == 16:
        if write_offset + MODEL_TRANSFORM_RECORD.size > len(payload):
            payload.extend(_EMPTY_MODEL_TRANSFORM_RECORD)
        try:
            MODEL_TRANSFORM_RECORD.pack_into(payload, write_offset, *transform)
        except (StructError, TypeError):
            pass
        else:
            return write_offset + MODEL_TRANSFORM_RECORD.size

    packed = pack_model_transform(transform)
    write_end = write_offset + len(packed)
    payload[write_offset:write_end] = packed
    return write_end


def append_model_translation_quaternion(
    payload: bytearray,
    tx: float,
    ty: float,
    tz: float,
    w: float,
    x: float,
    y: float,
    z: float,
    *,
    offset: int | None = None,
) -> int:
    """Write a compact transform directly into retained payload storage."""
    write_offset = len(payload) if offset is None else offset
    if write_offset + MODEL_TRANSLATION_QUATERNION_RECORD.size > len(payload):
        payload.extend(_EMPTY_MODEL_TRANSLATION_QUATERNION_RECORD)
    MODEL_TRANSLATION_QUATERNION_RECORD.pack_into(
        payload,
        write_offset,
        tx,
        ty,
        tz,
        w,
        x,
        y,
        z,
    )
    return write_offset + MODEL_TRANSLATION_QUATERNION_RECORD.size


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


def pack_image_commands(
    commands: Sequence[
        tuple[
            object,
            float,
            float,
            float,
            float,
            tuple[int, int, int, int] | None,
            MatrixPayload,
        ]
    ],
) -> tuple[bytes, list[object]]:
    """Pack one ordered image submission without retaining Python frame state."""

    records = bytearray(IMAGE_RECORD.size * len(commands))
    images: list[object] = []
    image_indices: dict[int, int] = {}
    for index, (rust_image, dx, dy, dw, dh, source, matrix) in enumerate(commands):
        key = int(cast(RustImageHandle, rust_image).key)
        image_index = image_indices.get(key)
        if image_index is None:
            image_index = len(images)
            image_indices[key] = image_index
            images.append(rust_image)
        IMAGE_RECORD.pack_into(
            records,
            index * IMAGE_RECORD.size,
            image_index,
            1 if source is not None else 0,
            float(dx),
            float(dy),
            float(dw),
            float(dh),
            *(source or (0, 0, 0, 0)),
            *matrix,
        )
    return bytes(records), images


def pack_text_commands(items: Sequence[tuple[str, float, float]]) -> tuple[bytes, bytes]:
    """Pack text placements and one UTF-8 blob without a Python frame queue."""

    records = bytearray(TEXT_RECORD.size * len(items))
    utf8 = bytearray()
    for index, (value, x, y) in enumerate(items):
        encoded = value.encode("utf-8")
        offset = len(utf8)
        utf8.extend(encoded)
        TEXT_RECORD.pack_into(
            records,
            index * TEXT_RECORD.size,
            offset,
            len(encoded),
            float(x),
            float(y),
        )
    return bytes(records), bytes(utf8)
