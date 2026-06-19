"""Font abstraction for p5-py text APIs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from p5.assets._paths import resolve_asset_path
from p5.exceptions import ArgumentValidationError, UnsupportedFeatureError


@dataclass(frozen=True, slots=True)
class Font:
    path: Path | None = None
    name: str | None = None

    def text_to_points(self, *args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        raise UnsupportedFeatureError(
            "Font.text_to_points() is deferred until p5-py has native font outline and "
            "shaping support in the Rust canvas runtime."
        )

    def text_to_paths(self, *args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        raise UnsupportedFeatureError(
            "Font.text_to_paths() is deferred until p5-py has native font outline and "
            "shaping support in the Rust canvas runtime."
        )

    def text_to_contours(self, *args: object, **kwargs: object) -> list[object]:
        del args, kwargs
        raise UnsupportedFeatureError(
            "Font.text_to_contours() is deferred until p5-py has native font outline and "
            "shaping support in the Rust canvas runtime."
        )

    def text_to_model(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        raise UnsupportedFeatureError(
            "Font.text_to_model() is deferred until p5-py has native font outline and "
            "shaping support in the Rust canvas runtime."
        )


def load_font(path: str | Path) -> Font:
    font_path = resolve_asset_path(path)
    if not font_path.exists():
        raise ArgumentValidationError(f"Font file does not exist: {font_path!s}.")
    return Font(path=font_path)


DEFAULT_FONT = Font(name="default")

__all__ = ["Font", "DEFAULT_FONT", "load_font"]
