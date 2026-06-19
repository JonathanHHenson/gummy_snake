"""Lightweight text and JSON loading/saving helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from p5.assets._paths import resolve_asset_path


def load_strings(path: str | Path, *, encoding: str = "utf-8") -> list[str]:
    return resolve_asset_path(path).read_text(encoding=encoding).splitlines()


def save_strings(
    values: list[str] | tuple[str, ...], path: str | Path, *, encoding: str = "utf-8"
) -> None:
    Path(path).write_text("\n".join(str(value) for value in values), encoding=encoding)


def load_json(path: str | Path, *, encoding: str = "utf-8") -> Any:
    return json.loads(resolve_asset_path(path).read_text(encoding=encoding))


def save_json(value: Any, path: str | Path, *, encoding: str = "utf-8", indent: int = 2) -> None:
    Path(path).write_text(json.dumps(value, indent=indent, ensure_ascii=False), encoding=encoding)


__all__ = ["load_strings", "save_strings", "load_json", "save_json"]
