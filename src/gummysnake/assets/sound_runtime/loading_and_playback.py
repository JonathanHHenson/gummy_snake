"""Sound loading helpers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.assets.sound_runtime.canvas_sound import CanvasSound
from gummysnake.assets.sound_runtime.sound import Sound
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


def load_sound(path: str | Path) -> Sound:
    """Load a sound file for playback and byte access.

    Args:
        path: File path or package-relative asset path to an existing sound.

    Returns:
        A Sound object with playback controls and metadata.
    """
    sound_path = resolve_asset_path(path)
    if not sound_path.exists():
        raise ArgumentValidationError(f"Sound file does not exist: {sound_path!s}.")
    try:
        rust_sound = CanvasSound.from_file(sound_path)
    except BackendCapabilityError:
        raise
    except Exception as exc:
        raise ArgumentValidationError(f"Could not load sound {sound_path!s}.") from exc
    return Sound(rust_sound, path=sound_path, rust_sound=rust_sound)


async def load_sound_async(path: str | Path) -> Sound:
    """Load a sound file using the async asset-loading API.

    Args:
        path: File path or package-relative asset path to an existing sound.

    Returns:
        A Sound object with playback controls and metadata.
    """
    return load_sound(path)


__all__ = ["load_sound", "load_sound_async"]
