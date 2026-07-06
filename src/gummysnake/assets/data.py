"""Lightweight text, bytes, writer, and JSON loading/saving helpers."""

from __future__ import annotations

import json
from pathlib import Path

from gummysnake.assets._paths import resolve_asset_path

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type BytesLike = bytes | bytearray | memoryview | list[int] | tuple[int, ...]


class Writer:
    """Small text writer for local Python file workflows."""

    def __init__(self, path: str | Path, *, encoding: str = "utf-8", append: bool = False) -> None:
        """Open a text file for writing or appending.

        Args:
            path: Destination text file path.
            encoding: Text encoding used when opening the file.
            append: Add to the end of the file instead of replacing it.
        """
        mode = "a" if append else "w"
        self.path = Path(path)
        self._file = self.path.open(mode, encoding=encoding)

    @property
    def closed(self) -> bool:
        """Return whether this writer's file handle is closed.

        Returns:
            ``True`` after ``close()`` has been called.
        """

        return self._file.closed

    def write(self, value: object = "") -> None:
        """Write text without adding a newline.

        Args:
            value: Value converted to text and written to the file.
        """

        self._file.write(str(value))

    def print(self, value: object = "") -> None:
        """Write text followed by a newline.

        Args:
            value: Value converted to text before the newline is added.
        """

        self._file.write(f"{value}\n")

    def close(self) -> None:
        """Close the underlying file handle."""

        self._file.close()

    def __enter__(self) -> Writer:
        """Return this writer for ``with`` statements.

        Returns:
            This ``Writer`` instance.
        """

        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the file when leaving a ``with`` block."""

        self.close()


def load_strings(path: str | Path, *, encoding: str = "utf-8") -> list[str]:
    """Load a text file as a list of lines.

    Args:
        path: Text file path or package-resource path.
        encoding: Text encoding used to read the file.

    Returns:
        Lines from the file without trailing newline characters.
    """

    return resolve_asset_path(path).read_text(encoding=encoding).splitlines()


async def load_strings_async(path: str | Path, *, encoding: str = "utf-8") -> list[str]:
    """Load text lines without blocking an async sketch callback.

    Args:
        path: Text file path or package-resource path.
        encoding: Text encoding used to read the file.

    Returns:
        Lines from the file without trailing newline characters.
    """

    return load_strings(path, encoding=encoding)


def save_strings(
    values: list[str] | tuple[str, ...], path: str | Path, *, encoding: str = "utf-8"
) -> None:
    """Save a sequence of strings as newline-separated text.

    Args:
        values: Strings to write, one per output line.
        path: Destination text file path.
        encoding: Text encoding used to write the file.
    """

    Path(path).write_text("\n".join(str(value) for value in values), encoding=encoding)


def load_json(path: str | Path, *, encoding: str = "utf-8") -> JsonValue:
    """Load a JSON file into Python lists, dictionaries, and scalar values.

    Args:
        path: JSON file path or package-resource path.
        encoding: Text encoding used to read the file.

    Returns:
        Parsed JSON data.
    """

    return json.loads(resolve_asset_path(path).read_text(encoding=encoding))


async def load_json_async(path: str | Path, *, encoding: str = "utf-8") -> JsonValue:
    """Load JSON without blocking an async sketch callback.

    Args:
        path: JSON file path or package-resource path.
        encoding: Text encoding used to read the file.

    Returns:
        Parsed JSON data.
    """

    return load_json(path, encoding=encoding)


def save_json(
    value: JsonValue, path: str | Path, *, encoding: str = "utf-8", indent: int = 2
) -> None:
    """Save JSON-compatible Python data to a file.

    Args:
        value: JSON-compatible value made from dictionaries, lists, strings,
            numbers, booleans, or ``None``.
        path: Destination JSON file path.
        encoding: Text encoding used to write the file.
        indent: Number of spaces used for pretty-printed indentation.
    """

    Path(path).write_text(json.dumps(value, indent=indent, ensure_ascii=False), encoding=encoding)


def load_bytes(path: str | Path) -> bytes:
    """Load a file as raw bytes.

    Args:
        path: File path or package-resource path.

    Returns:
        File contents as bytes.
    """

    return resolve_asset_path(path).read_bytes()


async def load_bytes_async(path: str | Path) -> bytes:
    """Load raw bytes without blocking an async sketch callback.

    Args:
        path: File path or package-resource path.

    Returns:
        File contents as bytes.
    """

    return load_bytes(path)


def save_bytes(values: BytesLike, path: str | Path) -> None:
    """Save raw byte values to a file.

    Args:
        values: Bytes-like value or a sequence of byte integers.
        path: Destination file path.
    """

    Path(path).write_bytes(bytes(values))


def create_writer(path: str | Path, *, encoding: str = "utf-8", append: bool = False) -> Writer:
    """Create a small text writer for incremental file output.

    Args:
        path: Destination text file path.
        encoding: Text encoding used when opening the file.
        append: Add to the end of the file instead of replacing it.

    Returns:
        A ``Writer`` that should be closed when writing is complete.
    """

    return Writer(path, encoding=encoding, append=append)


__all__ = [
    "Writer",
    "BytesLike",
    "JsonValue",
    "load_strings",
    "load_strings_async",
    "save_strings",
    "load_json",
    "load_json_async",
    "save_json",
    "load_bytes",
    "load_bytes_async",
    "save_bytes",
    "create_writer",
]
