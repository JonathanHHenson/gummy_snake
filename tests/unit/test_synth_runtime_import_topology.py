"""Import and public-identity regression tests for the synth runtime topology."""

from __future__ import annotations

import importlib
from pathlib import Path

from gummysnake import synth as sy
from gummysnake.synth import core

_RUNTIME_DIR = Path(__file__).parents[2] / "src/gummysnake/synth/synth_runtime"
_INTERNAL_AREAS = {
    "composition": (
        "builder_context",
        "context_managers",
        "definitions",
        "event_api",
        "logical_nodes",
        "plan_builder",
        "track_decorator",
    ),
    "values": (
        "expressions",
        "foundation",
        "lazy_values",
        "pattern_helpers",
        "scales_and_specs",
    ),
    "physical": ("physical_plan", "rendering", "serialization"),
    "playback_export": ("playback", "samples_and_export", "track"),
}
_LEGACY_TO_CANONICAL = {
    "builder_context": "composition.builder_context",
    "context_managers": "composition.context_managers",
    "definitions": "composition.definitions",
    "event_api": "composition.event_api",
    "expressions": "values.expressions",
    "lazy_values": "values.lazy_values",
    "logical_nodes": "composition.logical_nodes",
    "pattern_helpers": "values.pattern_helpers",
    "physical_plan": "physical.physical_plan",
    "plan_builder": "composition.plan_builder",
    "playback": "playback_export.playback",
    "rendering": "physical.rendering",
    "runtime_foundation": "values.foundation",
    "samples_and_export": "playback_export.samples_and_export",
    "scales_and_specs": "values.scales_and_specs",
    "serialization": "physical.serialization",
    "track": "playback_export.track",
    "track_decorator": "composition.track_decorator",
}


def test_synth_runtime_uses_documented_internal_areas_without_stem_collisions() -> None:
    """The 19 compatibility modules forward to four non-colliding implementation areas."""

    legacy_modules = tuple(
        sorted(path.stem for path in _RUNTIME_DIR.glob("*.py") if path.stem != "__init__")
    )

    assert legacy_modules == tuple(sorted(_LEGACY_TO_CANONICAL))
    assert set(_INTERNAL_AREAS) == {
        path.name for path in _RUNTIME_DIR.iterdir() if path.is_dir() and path.name != "__pycache__"
    }
    assert not [name for name in legacy_modules if (_RUNTIME_DIR / name).is_dir()]
    for area, modules in _INTERNAL_AREAS.items():
        assert (_RUNTIME_DIR / area / "__init__.py").is_file()
        assert {
            path.stem for path in (_RUNTIME_DIR / area).glob("*.py") if path.stem != "__init__"
        } == set(modules)


def test_legacy_runtime_modules_forward_to_the_canonical_implementation_objects() -> None:
    """Compatibility imports preserve every implementation object identity."""

    for legacy_name, canonical_name in _LEGACY_TO_CANONICAL.items():
        legacy_module = importlib.import_module(f"gummysnake.synth.synth_runtime.{legacy_name}")
        canonical_module = importlib.import_module(
            f"gummysnake.synth.synth_runtime.{canonical_name}"
        )
        for name, value in vars(canonical_module).items():
            if not name.startswith("__"):
                assert getattr(legacy_module, name) is value, f"{legacy_name}.{name}"


def test_public_synth_exports_retain_identity_and_legacy_metadata() -> None:
    """The 60-name synth facade remains an identity-preserving compatibility surface."""

    assert len(sy.__all__) == 60
    assert sy.__all__ == core.__all__
    for name in sy.__all__:
        assert getattr(sy, name) is getattr(core, name), name

    assert sy.Track.__module__ == "gummysnake.synth.synth_runtime.track"
    assert sy.PhysicalPlan.__module__ == "gummysnake.synth.synth_runtime.physical_plan"
    assert sy.track.__module__ == "gummysnake.synth.synth_runtime.track_decorator"
