"""Python-native Gummy Snake-style data conversion and formatting helpers."""

from __future__ import annotations

import builtins
import random as _random
import re
from collections.abc import MutableSequence, Sequence
from typing import Any

_TOKEN_RE = re.compile(r"[^\s,]+")


def boolean(value: Any) -> bool:
    """Return a Gummy Snake-compatible boolean conversion.

    Strings commonly used by p5.js examples are handled explicitly; other values
    follow Python truthiness.
    """

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    return bool(value)


def byte(value: int | float | str | bool) -> int:
    """Convert a value to an unsigned 8-bit integer using wraparound semantics."""

    return int(float(value)) & 0xFF


def char(value: int | str) -> str:
    """Convert a code point or first-character string to a one-character string."""

    if isinstance(value, str):
        if not value:
            raise ValueError("char() cannot convert an empty string.")
        return value[0]
    return chr(int(value))


def float_(value: Any) -> float:
    return builtins.float(value)


def int_(value: Any, base: int = 10) -> int:
    if isinstance(value, str):
        return builtins.int(value.strip(), base)
    return builtins.int(value)


def str_(value: Any) -> str:
    return builtins.str(value)


def hex_(value: int, digits: int | None = None) -> str:
    """Return uppercase hexadecimal without a prefix, padded when requested."""

    result = format(int(value) & 0xFFFFFFFF, "X")
    return result.zfill(int(digits)) if digits is not None else result


def unhex(value: str | Sequence[str]) -> int | list[int]:
    if isinstance(value, str):
        return builtins.int(value.strip().removeprefix("0x"), 16)
    return [builtins.int(item.strip().removeprefix("0x"), 16) for item in value]


def unchar(value: str | Sequence[str]) -> int | list[int]:
    if isinstance(value, str):
        if not value:
            raise ValueError("unchar() cannot convert an empty string.")
        return ord(value[0])
    return [ord(item[0]) for item in value]


def nf(value: int | float, left: int = 0, right: int | None = None) -> str:
    """Format a number with optional left zero padding and fixed decimals."""

    number = float(value)
    sign = "-" if number < 0 else ""
    magnitude = abs(number)
    if right is None:
        body = f"{int(round(magnitude)):0{int(left)}d}"
    else:
        body = f"{magnitude:0{int(left)}.{int(right)}f}"
    return sign + body


def nfc(value: int | float, right: int | None = None) -> str:
    if right is None:
        return f"{int(round(float(value))):,}"
    return f"{float(value):,.{int(right)}f}"


def nfp(value: int | float, left: int = 0, right: int | None = None) -> str:
    formatted = nf(abs(float(value)), left, right)
    return ("+" if float(value) >= 0 else "-") + formatted.lstrip("-")


def nfs(value: int | float, left: int = 0, right: int | None = None) -> str:
    formatted = nf(abs(float(value)), left, right)
    return (" " if float(value) >= 0 else "-") + formatted.lstrip("-")


def shuffle[T](values: Sequence[T], *, in_place: bool = False) -> list[T] | MutableSequence[T]:
    """Shuffle values using Python's RNG.

    By default this returns a shuffled list, matching Python expectations and
    avoiding mutation surprises. Pass ``in_place=True`` for mutable sequences.
    """

    if in_place:
        if not isinstance(values, MutableSequence):
            raise TypeError("shuffle(..., in_place=True) requires a mutable sequence.")
        _random.shuffle(values)
        return values
    result = list(values)
    _random.shuffle(result)
    return result


def split_tokens(value: str, delimiters: str | None = None) -> list[str]:
    if delimiters is None:
        return _TOKEN_RE.findall(value)
    pattern = f"[{' '.join(re.escape(char) for char in delimiters)}]+"
    return [token for token in re.split(pattern, value) if token]


__all__ = [
    "boolean",
    "byte",
    "char",
    "float_",
    "hex_",
    "int_",
    "str_",
    "unchar",
    "unhex",
    "nf",
    "nfc",
    "nfp",
    "nfs",
    "shuffle",
    "split_tokens",
]
