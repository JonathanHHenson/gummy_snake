"""Font abstraction for Gummy Snake text APIs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.exceptions import ArgumentValidationError, UnsupportedFeatureError


@dataclass(frozen=True, slots=True)
class Font:
    """Public Font value for Gummy Snake text features."""
    path: Path | None = None
    name: str | None = None

    def text_to_points(self, *args: object, **kwargs: object) -> list[object]:
        """Text to points for this Font.
        
        Args:
            *args: Additional positional arguments. Expected type: `object`.
            **kwargs: Additional keyword arguments. Expected type: `object`.
        
        Returns:
            The return value. Type: `list[object]`.
        """
        del args, kwargs
        raise UnsupportedFeatureError(
            "Font.text_to_points() is deferred until Gummy Snake has native font outline and "
            "shaping support in the Rust canvas runtime."
        )

    def text_to_paths(self, *args: object, **kwargs: object) -> list[object]:
        """Text to paths for this Font.
        
        Args:
            *args: Additional positional arguments. Expected type: `object`.
            **kwargs: Additional keyword arguments. Expected type: `object`.
        
        Returns:
            The return value. Type: `list[object]`.
        """
        del args, kwargs
        raise UnsupportedFeatureError(
            "Font.text_to_paths() is deferred until Gummy Snake has native font outline and "
            "shaping support in the Rust canvas runtime."
        )

    def text_to_contours(self, *args: object, **kwargs: object) -> list[object]:
        """Text to contours for this Font.
        
        Args:
            *args: Additional positional arguments. Expected type: `object`.
            **kwargs: Additional keyword arguments. Expected type: `object`.
        
        Returns:
            The return value. Type: `list[object]`.
        """
        del args, kwargs
        raise UnsupportedFeatureError(
            "Font.text_to_contours() is deferred until Gummy Snake has native font outline and "
            "shaping support in the Rust canvas runtime."
        )

    def text_to_model(self, *args: object, **kwargs: object) -> object:
        """Text to model for this Font.
        
        Args:
            *args: Additional positional arguments. Expected type: `object`.
            **kwargs: Additional keyword arguments. Expected type: `object`.
        
        Returns:
            The return value. Type: `object`.
        """
        del args, kwargs
        raise UnsupportedFeatureError(
            "Font.text_to_model() is deferred until Gummy Snake has native font outline and "
            "shaping support in the Rust canvas runtime."
        )


def load_font(path: str | Path) -> Font:
    """Load and return font.
    
    Args:
        path: The path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Font`.
    """
    font_path = resolve_asset_path(path)
    if not font_path.exists():
        raise ArgumentValidationError(f"Font file does not exist: {font_path!s}.")
    return Font(path=font_path)


async def load_font_async(path: str | Path) -> Font:
    """Load and return a font asynchronously.
    
    Args:
        path: The path value. Expected type: `str | Path`.
    
    Returns:
        The return value. Type: `Font`.
    """
    return load_font(path)


DEFAULT_FONT = Font(name="default")

__all__ = ["Font", "DEFAULT_FONT", "load_font", "load_font_async"]
