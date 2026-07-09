"""ECS physical execution compatibility module.

Helper modules keep this public module path stable.
"""

from __future__ import annotations
import __future__

from importlib import resources
from typing import Any

_PART_FILES = (
    "planning.py",
    "execution_reports.py",
    "canvas_dispatch.py",
)


def _load_physical_execution() -> None:
    package = f"{__package__}.physical_execution"
    flags = __future__.annotations.compiler_flag
    for name in _PART_FILES:
        source_path = resources.files(package).joinpath(name)
        source = source_path.read_text()
        code = compile(source, str(source_path), "exec", flags=flags, dont_inherit=True)
        exec(code, globals())


_load_physical_execution()
del _load_physical_execution


def __getattr__(name: str) -> Any:
    """Return dynamically loaded module attributes for static type checkers."""

    try:
        return globals()[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
