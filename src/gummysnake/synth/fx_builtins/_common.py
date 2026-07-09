"""Shared helpers for bundled source-defined FX."""

from __future__ import annotations

from gummysnake import synth as sy


def module_name(name: str) -> str:
    """Return the Python module/function stem for a Sonic Pi FX key."""

    return name.replace("-", "_")


def fx_duration(name: str) -> sy.Duration:
    """Return the bounded compile duration for a bundled FX definition."""

    if name in {"gverb", "reverb", "echo", "flanger"}:
        return sy.duration(secs=1.0)
    if name in {"slicer", "panslicer", "wobble", "ixi_techno"}:
        return sy.duration(secs=0.6)
    return sy.duration(secs=0.3)
