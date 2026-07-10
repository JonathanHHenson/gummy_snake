"""Logical-track synth composition and deterministic audio rendering."""

from __future__ import annotations

import builtins
import contextlib
import functools
import io
import json
import random as _random
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
import zlib
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self, SupportsIndex, cast, overload

from gummysnake.assets._audio_codec import MemorySoundSource
from gummysnake.assets.sound import Sound
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError, GummySnakeError

type Number = int | float
_SAMPLE_RATE = 44_100


def _builtin_sample_package_dir() -> Path:
    current_file = Path(__file__).resolve()
    parents = current_file.parents
    candidates = []
    if len(parents) > 4:
        candidates.append(parents[4] / "assets" / "samples" / "sonic_pi")
    if len(parents) > 3:
        candidates.append(parents[3] / "assets" / "samples" / "sonic_pi")
    if len(parents) > 2:
        candidates.append(parents[2] / "assets" / "samples" / "sonic_pi")
    if len(parents) > 1:
        candidates.append(parents[1] / "assets" / "samples" / "sonic_pi")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else current_file.parent / "assets" / "samples" / "sonic_pi"


_BUILTIN_SAMPLE_PACKAGE_DIR = _builtin_sample_package_dir()
_BUILTIN_SAMPLE_EXTENSIONS = (".flac", ".wav", ".aif", ".aiff", ".wave")
_PHYSICAL_PLAN_SCHEMA = "gummysnake.synth.physical_plan.v1"
_GSS_MAGIC = b"GSSPLAN\x01"
_GSS_HEADER = struct.Struct(">8sII")
_GSS_COMPRESSION = 1


def _asset_dir(*parts: str) -> Path:
    current_file = Path(__file__).resolve()
    parents = current_file.parents
    candidates = []
    if len(parents) > 4:
        candidates.append(parents[4].joinpath(*parts))
    if len(parents) > 3:
        candidates.append(parents[3].joinpath(*parts))
    if len(parents) > 2:
        candidates.append(parents[2].joinpath(*parts))
    if len(parents) > 1:
        candidates.append(parents[1].joinpath(*parts))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else current_file.parent.joinpath(*parts)


_BUILTIN_SYNTH_COMPILED_DIR = _asset_dir("assets", "synths", "compiled")
_BUILTIN_FX_COMPILED_DIR = _asset_dir("assets", "fx", "compiled")


def _as_float(value: object) -> float:
    return float(cast(Any, value))


def _as_int(value: object) -> int:
    return int(cast(Any, value))


class SynthPlanError(GummySnakeError):
    """Raised when synth logical-plan construction fails."""


class Format(StrEnum):
    """File formats supported by ``Track.save``."""

    WAV = "wav"
    MP3 = "mp3"
    GSS = "gss"
    GSFX = "gsfx"


@dataclass(frozen=True, slots=True)
class Duration:
    """Concrete render duration.

    Durations are stored in seconds because rendered media is wall-clock audio.
    Helpers such as :func:`duration` can still express values in beats using a
    BPM conversion.
    """

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds < 0:
            raise ArgumentValidationError("duration cannot be negative.")

    @property
    def beats(self) -> float:
        """Duration in beats at the default 60 BPM."""

        return self.seconds

    def __float__(self) -> float:
        return self.seconds


def duration(
    *,
    hours: float = 0.0,
    mins: float = 0.0,
    secs: float = 0.0,
    beats: float = 0.0,
    bpm: float = 60.0,
) -> Duration:
    """Create a render duration from clock units and/or beats.

    Args:
        hours: Hours to include.
        mins: Minutes to include.
        secs: Seconds to include.
        beats: Beat count to convert using ``bpm``.
        bpm: Tempo used for beat conversion.

    Returns:
        A concrete :class:`Duration`.
    """

    if bpm <= 0:
        raise ArgumentValidationError("duration bpm must be positive.")
    total = hours * 3600.0 + mins * 60.0 + secs + beats * 60.0 / bpm
    return Duration(float(total))


_EXPRESSION_COUNTER = 0


def _next_expression_id() -> int:
    global _EXPRESSION_COUNTER
    _EXPRESSION_COUNTER += 1
    return _EXPRESSION_COUNTER


def _current_repeat_depth_or_none() -> int | None:
    from gummysnake.synth.synth_runtime.builder_context import _CURRENT_BUILDER

    builder = _CURRENT_BUILDER.get()
    if builder is None:
        return None
    return builder.repeat_depth


def _binary_expression(op: str, left: object, right: object) -> Expression:
    from gummysnake.synth.synth_runtime.expressions import BinaryExpression
    from gummysnake.synth.synth_runtime.lazy_values import ensure_expr

    return BinaryExpression(op, ensure_expr(left), ensure_expr(right))


def _compare_expression(op: str, left: object, right: object) -> Expression:
    from gummysnake.synth.synth_runtime.expressions import CompareExpression
    from gummysnake.synth.synth_runtime.lazy_values import ensure_expr

    return CompareExpression(op, ensure_expr(left), ensure_expr(right))


def _unary_expression(op: str, operand: Expression) -> Expression:
    from gummysnake.synth.synth_runtime.expressions import UnaryExpression

    return UnaryExpression(op, operand)


@dataclass(slots=True)
class EvalContext:
    """State used when evaluating logical expressions."""

    rng: _random.Random
    ticks: dict[str, int] = field(default_factory=dict)
    scope: tuple[object, ...] = ()
    repeat_scope: tuple[object, ...] = ()
    bindings: dict[tuple[str, tuple[object, ...], int], object] = field(default_factory=dict)


class Expression:
    """Base class for lazily evaluated synth-plan values."""

    def evaluate(self, ctx: EvalContext) -> object:
        raise NotImplementedError

    def __bool__(self) -> bool:
        raise SynthPlanError(
            "Synth expressions are lazy and cannot be used as Python booleans. "
            "Use .when(expr), sy.when(...), or arithmetic/comparison expressions."
        )

    def __add__(self, other: object) -> Expression:
        return _binary_expression("add", self, other)

    def __radd__(self, other: object) -> Expression:
        return _binary_expression("add", other, self)

    def __sub__(self, other: object) -> Expression:
        return _binary_expression("sub", self, other)

    def __rsub__(self, other: object) -> Expression:
        return _binary_expression("sub", other, self)

    def __mul__(self, other: object) -> Expression:
        return _binary_expression("mul", self, other)

    def __rmul__(self, other: object) -> Expression:
        return _binary_expression("mul", other, self)

    def __truediv__(self, other: object) -> Expression:
        return _binary_expression("truediv", self, other)

    def __rtruediv__(self, other: object) -> Expression:
        return _binary_expression("truediv", other, self)

    def __mod__(self, other: object) -> Expression:
        return _binary_expression("mod", self, other)

    def __rmod__(self, other: object) -> Expression:
        return _binary_expression("mod", other, self)

    def __pow__(self, other: object) -> Expression:
        return _binary_expression("pow", self, other)

    def __rpow__(self, other: object) -> Expression:
        return _binary_expression("pow", other, self)

    def __neg__(self) -> Expression:
        return _unary_expression("neg", self)

    def __lt__(self, other: object) -> Expression:
        return _compare_expression("lt", self, other)

    def __le__(self, other: object) -> Expression:
        return _compare_expression("le", self, other)

    def __gt__(self, other: object) -> Expression:
        return _compare_expression("gt", self, other)

    def __ge__(self, other: object) -> Expression:
        return _compare_expression("ge", self, other)

    def __eq__(self, other: object) -> Expression:  # type: ignore[override]
        return _compare_expression("eq", self, other)

    def __ne__(self, other: object) -> Expression:  # type: ignore[override]
        return _compare_expression("ne", self, other)
