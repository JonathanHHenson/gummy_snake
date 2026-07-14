"""Regression tests for the synth runtime's canonical package topology."""

from __future__ import annotations

from pathlib import Path

from gummysnake import synth as sy

_RUNTIME_DIR = Path(__file__).parents[3] / "src/gummysnake/synth/synth_runtime"
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
    "physical": ("execution", "physical_plan", "rendering", "serialization"),
    "playback_export": ("playback", "samples_and_export", "track"),
}


def test_synth_runtime_uses_only_canonical_internal_areas() -> None:
    """Runtime implementation belongs only to the four documented domain packages."""

    assert [path.name for path in _RUNTIME_DIR.glob("*.py") if path.name != "__init__.py"] == []
    assert set(_INTERNAL_AREAS) == {
        path.name for path in _RUNTIME_DIR.iterdir() if path.is_dir() and path.name != "__pycache__"
    }
    for area, modules in _INTERNAL_AREAS.items():
        assert (_RUNTIME_DIR / area / "__init__.py").is_file()
        assert {
            path.stem for path in (_RUNTIME_DIR / area).glob("*.py") if path.stem != "__init__"
        } == set(modules)


def test_public_synth_exports_retain_identity_and_canonical_metadata() -> None:
    """The public facade keeps its exports while exposing their canonical owners."""

    assert len(sy.__all__) == 64

    assert sy.Track.__module__ == "gummysnake.synth.synth_runtime.playback_export.track"
    assert sy.PhysicalPlan.__module__ == "gummysnake.synth.synth_runtime.physical.physical_plan"
    assert sy.configure_workers.__module__ == "gummysnake.synth.synth_runtime.physical.execution"
    assert sy.synth_diagnostics.__module__ == "gummysnake.synth.synth_runtime.physical.execution"
    assert sy.track.__module__ == "gummysnake.synth.synth_runtime.composition.track_decorator"
