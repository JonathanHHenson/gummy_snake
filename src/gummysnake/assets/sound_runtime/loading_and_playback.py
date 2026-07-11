"""Legacy loader import path forwarding to the public sound authority.

New code must import loaders from :mod:`gummysnake.assets.sound`.  Keeping this
module as a delegating shim preserves deliberate compatibility for integrations
that imported the former internal path, without creating a second loader.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gummysnake.assets.sound import Sound


def load_sound(path: str | Path) -> Sound:
    """Delegate to the stable public sound loader."""

    from gummysnake.assets.sound import load_sound as public_load_sound

    return public_load_sound(path)


async def load_sound_async(path: str | Path) -> Sound:
    """Delegate to the stable public asynchronous sound loader."""

    from gummysnake.assets.sound import load_sound_async as public_load_sound_async

    return await public_load_sound_async(path)


__all__ = ["load_sound", "load_sound_async"]
