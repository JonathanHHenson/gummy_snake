"""Stable public sound assets and loaders.

``Sound``, ``CanvasSound``, ``load_sound``, and ``load_sound_async`` are the
public compatibility surface.  Native player implementation details live in
``sound_runtime.native_playback``; private hook aliases below deliberately
remain available for existing test and integration monkeypatches.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from gummysnake.assets._paths import resolve_asset_path
from gummysnake.assets.sound_runtime.canvas_sound import CanvasSound
from gummysnake.assets.sound_runtime.native_playback import (
    NativeAudioPlayer,
)
from gummysnake.assets.sound_runtime.native_playback import (
    platform_play_command as _native_platform_play_command,
)
from gummysnake.assets.sound_runtime.native_playback import (
    stop_active_native_audio_players as _stop_active_native_audio_players,
)
from gummysnake.assets.sound_runtime.sound import Sound as _RuntimeSound
from gummysnake.exceptions import ArgumentValidationError, BackendCapabilityError


def _platform_play_command(path: Path) -> list[str] | None:
    """Return the selected platform-player command.

    This private compatibility hook is intentionally retained for integrations
    that instrument player selection.  Public code should use ``Sound.play()``.
    """

    return _native_platform_play_command(path)


class _NativeAudioPlayer(NativeAudioPlayer):
    """Compatibility player whose command hook resolves through this module."""

    def _play_command(self) -> list[str] | None:
        return _platform_play_command(self._path)


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
    """Load a sound file for playback and byte access.

    This is the authoritative sound-loading implementation.  It always returns
    the stable public ``Sound`` type backed by a Rust-managed ``CanvasSound``.
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
