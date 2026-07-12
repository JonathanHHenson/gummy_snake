"""Canvas export helpers for SketchContext pixel APIs."""

from __future__ import annotations

from collections.abc import Callable
from math import isfinite
from pathlib import Path
from typing import Protocol

from gummysnake.assets.image.exporting import png_export_path
from gummysnake.core.pixels import FrameSaveInfo
from gummysnake.exceptions import ArgumentValidationError


class _CanvasExportRenderer(Protocol):
    def save(self, path: Path) -> None: ...

    def save_gif(self, path: Path, count: int, frame_duration_ms: int) -> None: ...


class _CanvasExportTiming(Protocol):
    target_frame_rate: float
    frame_count: int


class _CanvasExportState(Protocol):
    timing: _CanvasExportTiming


class _CanvasExportContext(Protocol):
    renderer: _CanvasExportRenderer
    state: _CanvasExportState

    def save_canvas(
        self, path: str | Path, *, extension: str | None = None, overwrite: bool = True
    ) -> Path: ...


def save_canvas(
    ctx: _CanvasExportContext,
    path: str | Path,
    *,
    extension: str | None = None,
    overwrite: bool = True,
) -> Path:
    output = Path(path)
    if extension is not None:
        suffix = extension if extension.startswith(".") else f".{extension}"
        output = output.with_suffix(suffix.lower())
    output = png_export_path(output, operation="save_canvas()")
    if output.exists() and not overwrite:
        raise ArgumentValidationError(f"Refusing to overwrite existing file: {output!s}.")
    output.parent.mkdir(parents=True, exist_ok=True)
    ctx.renderer.save(output)
    return output


def save_frames(
    ctx: _CanvasExportContext,
    path_pattern: str | Path,
    *,
    extension: str = "png",
    count: int = 1,
    duration: float | None = None,
    callback: Callable[[list[FrameSaveInfo]], None] | None = None,
    overwrite: bool = True,
) -> list[FrameSaveInfo]:
    if count <= 0:
        raise ArgumentValidationError("save_frames() count must be positive.")
    suffix = extension if extension.startswith(".") else f".{extension}"
    frame_duration = (
        1.0 / ctx.state.timing.target_frame_rate if duration is None else float(duration) / count
    )
    pattern = str(path_pattern)
    results: list[FrameSaveInfo] = []
    for index in range(count):
        if "{" in pattern:
            output = Path(
                pattern.format(
                    index=index,
                    frame=index,
                    frame_count=ctx.state.timing.frame_count,
                )
            )
        else:
            stem = Path(pattern)
            output = stem.with_name(f"{stem.stem}_{index:04d}{stem.suffix or suffix}")
        if output.suffix == "":
            output = output.with_suffix(suffix)
        saved = ctx.save_canvas(output, overwrite=overwrite)
        results.append(
            {
                "path": saved,
                "frame": index,
                "frame_count": ctx.state.timing.frame_count,
                "duration": frame_duration,
            }
        )
    if callback is not None:
        callback(results)
    return results


def save_gif(
    ctx: _CanvasExportContext,
    path: str | Path,
    *,
    count: int = 1,
    duration: float | None = None,
    overwrite: bool = True,
) -> Path:
    output = Path(path)
    if output.name in {"", "."}:
        raise ArgumentValidationError("save_gif() requires a file path, not a directory.")
    if output.suffix == "":
        output = output.with_suffix(".gif")
    elif output.suffix.lower() != ".gif":
        raise ArgumentValidationError(
            f"save_gif() supports only GIF output; received {output.suffix!r}."
        )
    if count <= 0:
        raise ArgumentValidationError("save_gif() count must be positive.")
    total_duration = (
        1.0 / ctx.state.timing.target_frame_rate if duration is None else float(duration)
    )
    if not isfinite(total_duration) or total_duration <= 0:
        raise ArgumentValidationError("save_gif() duration must be finite and positive.")
    frame_duration_ms = int(round(total_duration * 1000.0 / count))
    if frame_duration_ms <= 0:
        raise ArgumentValidationError(
            "save_gif() duration is too short to encode a positive frame duration."
        )
    if output.exists() and not overwrite:
        raise ArgumentValidationError(f"Refusing to overwrite existing file: {output!s}.")
    output.parent.mkdir(parents=True, exist_ok=True)
    ctx.renderer.save_gif(output, count, frame_duration_ms)
    return output
