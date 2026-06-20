"""Helpers for resolving asset paths in sketch code."""

from __future__ import annotations

import inspect
from pathlib import Path


def resolve_asset_path(path: str | Path) -> Path:
    """Resolve an asset path relative to the calling sketch when possible.

    Relative asset paths are first checked as-is. If they do not exist, the
    resolver walks back the call stack to find the first frame outside the
    ``gummysnake`` package and interprets the path relative to that module's directory.
    This keeps sketch-local asset references working even when the process is
    launched from a different working directory.
    """

    asset_path = Path(path)
    if asset_path.is_absolute() or asset_path.exists():
        return asset_path

    package_root = Path(__file__).resolve().parents[1]
    current_frame = inspect.currentframe()
    try:
        frame = current_frame.f_back if current_frame is not None else None
        while frame is not None:
            frame_path = Path(frame.f_code.co_filename)
            if frame_path.name == "<string>":
                frame = frame.f_back
                continue
            try:
                resolved_frame_path = frame_path.resolve()
            except OSError:
                frame = frame.f_back
                continue
            if package_root in resolved_frame_path.parents or resolved_frame_path == package_root:
                frame = frame.f_back
                continue
            candidate = resolved_frame_path.parent / asset_path
            if candidate.exists():
                return candidate
            frame = frame.f_back
    finally:
        del current_frame

    return asset_path
