"""Global-mode sound loading wrappers."""

from __future__ import annotations

from pathlib import Path

from gummysnake.assets.sound import Sound
from gummysnake.assets.sound import load_sound as _load_sound
from gummysnake.assets.sound import load_sound_async as _load_sound_async


def load_sound(path: str | Path) -> Sound:
    return _load_sound(path)


async def load_sound_async(path: str | Path) -> Sound:
    return await _load_sound_async(path)


def create_audio(path: str | Path) -> Sound:
    return _load_sound(path)


__all__ = [
    "load_sound",
    "load_sound_async",
    "create_audio",
]
