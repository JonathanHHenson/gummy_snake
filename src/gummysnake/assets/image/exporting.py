"""Validation for the Rust canvas runtime's supported still-image export format."""

from __future__ import annotations

from pathlib import Path

from gummysnake.exceptions import ArgumentValidationError

_PNG_SUFFIX = ".png"


def png_export_path(path: str | Path, *, operation: str) -> Path:
    """Return a PNG destination path or reject an unsupported still-image suffix."""
    output = Path(path)
    if output.name in {"", "."}:
        raise ArgumentValidationError(f"{operation} requires a file path, not a directory.")
    if output.suffix == "":
        return output.with_suffix(_PNG_SUFFIX)
    if output.suffix.lower() != _PNG_SUFFIX:
        raise ArgumentValidationError(
            f"{operation} supports only PNG output; received {output.suffix!r}."
        )
    return output


__all__ = ["png_export_path"]
