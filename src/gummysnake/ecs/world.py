"""ECS world facade compatibility module.

Helper modules keep this public module path stable.
"""

from __future__ import annotations
import __future__

from importlib import resources
from typing import Any

_PART_FILES = (
    "facade_context.py",
    "world.py",
    "state_methods.py",
    "exports.py",
)


def _load_world_facade() -> None:
    package = f"{__package__}.world_facade"
    flags = __future__.annotations.compiler_flag
    for name in _PART_FILES:
        source_path = resources.files(package).joinpath(name)
        source = source_path.read_text()
        code = compile(source, str(source_path), "exec", flags=flags, dont_inherit=True)
        exec(code, globals())


_load_world_facade()
del _load_world_facade


def __getattr__(name: str) -> Any:
    """Return dynamically loaded module attributes for static type checkers."""

    try:
        return globals()[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
