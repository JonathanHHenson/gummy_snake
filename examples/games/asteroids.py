"""Playable Asteroids-style demo using Kenney space shooter assets.

Run interactively with canvas:
    uv run python examples/games/asteroids.py --interactive

Run/export a deterministic preview without opening a window:
    uv run python examples/games/asteroids.py --headless --frames 1

Controls when interactive:
    A/D or left/right arrows rotate the ship.
    W or up arrow thrusts forward.
    Space or click fires a laser.
    R restarts after game over.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from asteroids_game import run

if __name__ == "__main__":
    run(__doc__)
