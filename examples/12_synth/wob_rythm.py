"""Compatibility entry point for the historical ``wob_rythm`` spelling."""

from __future__ import annotations

import importlib
from pathlib import Path

_canonical = importlib.import_module("wob_rhythm")
main = _canonical.main
wob_rhythm = _canonical.wob_rhythm

OUTPUT = Path("examples/output/12_synth/wob_rythm.wav")

# Keep the public callable and misspelled command path stable for this epic.
wob_rythm = wob_rhythm

__all__ = ["OUTPUT", "main", "wob_rythm"]


if __name__ == "__main__":
    main(default_output=OUTPUT, display_name="wob_rythm")
