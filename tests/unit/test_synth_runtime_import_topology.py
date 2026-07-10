"""Import-topology regression tests for the flat synth runtime."""

from __future__ import annotations

import importlib
from pathlib import Path

from gummysnake import synth as sy

_RUNTIME_DIR = Path(__file__).parents[2] / "src/gummysnake/synth/synth_runtime"


def test_flat_synth_runtime_modules_have_no_same_stem_packages() -> None:
    """Flat compatibility imports cannot be shadowed by same-named packages."""

    flat_modules = tuple(
        sorted(path.stem for path in _RUNTIME_DIR.glob("*.py") if path.stem != "__init__")
    )
    collisions = [name for name in flat_modules if (_RUNTIME_DIR / name).is_dir()]

    assert not collisions

    modules = {
        name: importlib.import_module(f"gummysnake.synth.synth_runtime.{name}")
        for name in flat_modules
    }
    assert sy.Track is modules["track"].Track
    assert sy.PhysicalPlan is modules["physical_plan"].PhysicalPlan
