"""Font abstraction for Gummy Snake text APIs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.exceptions import ArgumentValidationError, UnsupportedFeatureError

_FONT_OUTLINE_DEFERRED = (
    "is deferred until Gummy Snake has native font outline and shaping support in the "
    "Rust canvas runtime."
)


def _raise_deferred_font_outline(method: str) -> NoReturn:
    raise UnsupportedFeatureError(f"{method}() {_FONT_OUTLINE_DEFERRED}")


@dataclass(frozen=True, slots=True)
class Font:
    """Public Font value for Gummy Snake text features."""

    path: Path | None = None
    name: str | None = None

    def text_to_points(self, *args: object, **kwargs: object) -> list[object]:
        """Deferred font-outline point extraction."""
        del args, kwargs
        _raise_deferred_font_outline("Font.text_to_points")

    def text_to_paths(self, *args: object, **kwargs: object) -> list[object]:
        """Deferred font-outline path extraction."""
        del args, kwargs
        _raise_deferred_font_outline("Font.text_to_paths")

    def text_to_contours(self, *args: object, **kwargs: object) -> list[object]:
        """Deferred font-outline contour extraction."""
        del args, kwargs
        _raise_deferred_font_outline("Font.text_to_contours")

    def text_to_model(self, *args: object, **kwargs: object) -> object:
        """Deferred font-outline model extraction."""
        del args, kwargs
        _raise_deferred_font_outline("Font.text_to_model")


def load_font(path: str | Path) -> Font:
    font_path = resolve_asset_path(path)
    if not font_path.exists():
        raise ArgumentValidationError(f"Font file does not exist: {font_path!s}.")
    return Font(path=font_path)


async def load_font_async(path: str | Path) -> Font:
    return load_font(path)


DEFAULT_FONT = Font(name="default")

__all__ = ["Font", "DEFAULT_FONT", "load_font", "load_font_async"]
