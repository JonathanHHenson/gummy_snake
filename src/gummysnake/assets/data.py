"""Lightweight text, bytes, writer, and JSON loading/saving helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gummysnake.assets._paths import resolve_asset_path


class Writer:
    """Small text writer for local Python file workflows."""

    def __init__(self, path: str | Path, *, encoding: str = "utf-8", append: bool = False) -> None:
        """Open a text file for writing or appending."""
        mode = "a" if append else "w"
        self.path = Path(path)
        self._file = self.path.open(mode, encoding=encoding)

    @property
    def closed(self) -> bool:
        return self._file.closed

    def write(self, value: object = "") -> None:
        self._file.write(str(value))

    def print(self, value: object = "") -> None:
        self._file.write(f"{value}\n")

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> Writer:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def load_strings(path: str | Path, *, encoding: str = "utf-8") -> list[str]:
    return resolve_asset_path(path).read_text(encoding=encoding).splitlines()


async def load_strings_async(path: str | Path, *, encoding: str = "utf-8") -> list[str]:
    return load_strings(path, encoding=encoding)


def save_strings(
    values: list[str] | tuple[str, ...], path: str | Path, *, encoding: str = "utf-8"
) -> None:
    Path(path).write_text("\n".join(str(value) for value in values), encoding=encoding)


def load_json(path: str | Path, *, encoding: str = "utf-8") -> Any:
    return json.loads(resolve_asset_path(path).read_text(encoding=encoding))


async def load_json_async(path: str | Path, *, encoding: str = "utf-8") -> Any:
    return load_json(path, encoding=encoding)


def save_json(value: Any, path: str | Path, *, encoding: str = "utf-8", indent: int = 2) -> None:
    Path(path).write_text(json.dumps(value, indent=indent, ensure_ascii=False), encoding=encoding)


def load_bytes(path: str | Path) -> bytes:
    return resolve_asset_path(path).read_bytes()


async def load_bytes_async(path: str | Path) -> bytes:
    return load_bytes(path)


def save_bytes(
    values: bytes | bytearray | memoryview | list[int] | tuple[int, ...], path: str | Path
) -> None:
    Path(path).write_bytes(bytes(values))


def create_writer(path: str | Path, *, encoding: str = "utf-8", append: bool = False) -> Writer:
    return Writer(path, encoding=encoding, append=append)


__all__ = [
    "Writer",
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
