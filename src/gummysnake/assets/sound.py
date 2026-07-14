"""Stable public sound assets and native SDL playback loaders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.assets.sound_runtime.canvas_sound import CanvasSound
from gummysnake.assets.sound_runtime.sound import Sound as _RuntimeSound
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


class Sound(_RuntimeSound):
    """Rust-owned sound asset with process-local native SDL playback."""

    def __init__(
        self,
        source: object,
        *,
        path: Path,
        rust_sound: CanvasSound | None = None,
        player_factory: Any | None = None,
    ) -> None:
        super().__init__(
            source,
            path=path,
            rust_sound=rust_sound,
            player_factory=player_factory,
        )


def load_sound(path: str | Path) -> Sound:
    """Load a mono or stereo 16-bit PCM WAV into a Rust-owned audio asset.

    Loading and metadata access do not open an audio device. ``Sound.play()``
    opens or reuses the process-local SDL3 manager and fails clearly if native
    audio is unavailable.
    """

    sound_path = resolve_asset_path(path)
    if not sound_path.exists():
        raise ArgumentValidationError(f"Sound file does not exist: {sound_path!s}.")
    try:
        rust_sound = CanvasSound.from_file(sound_path)
    except BackendCapabilityError:
        raise
    except Exception as exc:
        raise ArgumentValidationError(
            f"Could not load sound {sound_path!s}; expected mono or stereo 16-bit PCM WAV audio."
        ) from exc
    return Sound(rust_sound, path=sound_path, rust_sound=rust_sound)


async def load_sound_async(path: str | Path) -> Sound:
    """Load a sound through the awaitable asset API using the same native asset path."""

    return load_sound(path)


__all__ = ["CanvasSound", "Sound", "load_sound", "load_sound_async"]
