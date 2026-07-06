"""Shared typing helpers for ECS values passed from Python."""

from __future__ import annotations

from dataclasses import Field
from typing import Any, ClassVar, Protocol


class DataclassInstance(Protocol):
    """A Python dataclass instance used as an ECS component, resource, or event.

    Gummy Snake validates dataclass payloads at runtime so it can map each field
    to Rust-owned ECS storage. This protocol describes the marker attribute that
    Python adds to dataclass instances.
    """

    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]


class SupportsStr(Protocol):
    """A value that can be converted to text with ``str(value)``."""

    def __str__(self) -> str:
        """Return the text form used by ECS tag storage.

        Returns:
            The string representation of this value.
        """
        ...


type EcsEventValue = DataclassInstance | bool | int | float | str
type EcsTag = SupportsStr


__all__ = ["DataclassInstance", "EcsEventValue", "EcsTag", "SupportsStr"]
