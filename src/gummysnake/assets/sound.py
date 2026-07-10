"""Sound runtime compatibility module.

Helper modules keep this public module path stable while preserving the small
private playback hooks used by tests and older integrations.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.assets.sound_runtime import sound as _sound_runtime
from gummysnake.assets.sound_runtime.canvas_sound import CanvasSound
from gummysnake.assets.sound_runtime.sound import Sound as _RuntimeSound
from gummysnake.assets.sound_runtime.sound import (
    _NativeAudioPlayer as _RuntimeNativeAudioPlayer,
)
from gummysnake.assets.sound_runtime.sound import (
    _platform_play_command as _runtime_platform_play_command,
)
from gummysnake.assets.sound_runtime.sound import (
    _stop_active_native_audio_players,
)
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


def _platform_play_command(path: Path) -> list[str] | None:
    return _runtime_platform_play_command(path)


class _NativeAudioPlayer(_RuntimeNativeAudioPlayer):
    def play(self) -> None:
        previous = _sound_runtime._platform_play_command
        _sound_runtime._platform_play_command = _platform_play_command
        try:
            super().play()
        finally:
            _sound_runtime._platform_play_command = previous


class Sound(_RuntimeSound):
    """Loaded sound asset with playback controls."""

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
            player_factory=player_factory or _NativeAudioPlayer,
        )


def load_sound(path: str | Path) -> Sound:
    """Load a sound file for playback and byte access."""

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
    """Load a sound file using the async asset-loading API."""

    return load_sound(path)


__all__ = [
    "CanvasSound",
    "Sound",
    "_NativeAudioPlayer",
    "_platform_play_command",
    "_stop_active_native_audio_players",
    "load_sound",
    "load_sound_async",
    "subprocess",
]
