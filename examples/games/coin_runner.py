"""Arcade side-scrolling runner using the hero, shield, UFO, and sound assets.

Run interactively with canvas:
    uv run python examples/games/coin_runner.py --interactive

Run/export a deterministic preview without opening a window:
    uv run python examples/games/coin_runner.py --headless --frames 1

Controls when interactive:
    Hold space, W, up arrow, or mouse for a higher jump.
    R restarts after a crash.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from coin_runner_game import run

if __name__ == "__main__":
    run(__doc__)
