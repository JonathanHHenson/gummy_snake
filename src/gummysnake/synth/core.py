"""Synth runtime compatibility module.

Helper modules keep this public module path stable.
"""

from __future__ import annotations
import __future__

from importlib import resources
from typing import Any

_PART_FILES = (
    "runtime_foundation.py",
    "expressions.py",
    "lazy_values.py",
    "pattern_helpers.py",
    "scales_and_specs.py",
    "logical_nodes.py",
    "physical_plan.py",
    "plan_builder.py",
    "builder_context.py",
    "context_managers.py",
    "event_api.py",
    "definitions.py",
    "track_decorator.py",
    "playback.py",
    "track.py",
    "rendering.py",
    "serialization.py",
    "samples_and_export.py",
)


def _load_synth_runtime() -> None:
    package = f"{__package__}.synth_runtime"
    flags = __future__.annotations.compiler_flag
    for name in _PART_FILES:
        source_path = resources.files(package).joinpath(name)
        source = source_path.read_text()
        code = compile(source, str(source_path), "exec", flags=flags, dont_inherit=True)
        exec(code, globals())


_load_synth_runtime()
del _load_synth_runtime


def __getattr__(name: str) -> Any:
    """Return dynamically loaded module attributes for static type checkers."""

    try:
        return globals()[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
