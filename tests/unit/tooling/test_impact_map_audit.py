from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "impact_map_audit.py"


def _load_audit() -> ModuleType:
    spec = importlib.util.spec_from_file_location("impact_map_audit", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


impact_map_audit = _load_audit()


class _Violation(Protocol):
    code: str
    location: str


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _categories() -> str:
    return "\n".join(
        f'{category} = ["N/A: this focused fixture does not require {category} coverage."]'
        for category in sorted(impact_map_audit.REQUIRED_CATEGORIES)
    )


def _map(paths: str = '["scripts/check.py"]', command: str = "python scripts/check.py") -> str:
    categories = _categories()
    categories_list = (
        '["unit", "contract", "integration", "golden", "stress", '
        '"example", "documentation", "packaging"]'
    )
    return f'''[map]
categories = {categories_list}

[checks.check]
focus = "behavior"
paths = {paths}
command = "{command}"

[areas.python]
source = ["src/gummysnake/current.py"]
roles = ["implementation"]
ownership = "Fixture Python source."
[areas.python.categories]
{categories}

[areas.one]
source = ["crates/one/Cargo.toml", "crates/one/src/**/*.rs"]
crate = "crates/one"
roles = ["implementation"]
ownership = "Fixture workspace crate."
[areas.one.categories]
{categories}
'''


def _workspace(tmp_path: Path, *, map_content: str | None = None) -> Path:
    _write(tmp_path / "Cargo.toml", '[workspace]\nmembers = ["crates/one"]\n')
    _write(tmp_path / "src/gummysnake/current.py", "VALUE = 1\n")
    _write(tmp_path / "crates/one/Cargo.toml", "[package]\nname = 'one'\n")
    _write(tmp_path / "crates/one/src/lib.rs", "pub fn one() {}\n")
    _write(tmp_path / "scripts/check.py", "print('ok')\n")
    map_path = tmp_path / "impact_map.toml"
    _write(map_path, _map() if map_content is None else map_content)
    return map_path


def _codes(violations: list[_Violation]) -> set[str]:
    return {violation.code for violation in violations}


def test_repository_impact_map_is_current() -> None:
    assert impact_map_audit.audit(ROOT) == []


def test_audit_rejects_empty_groups_and_stale_command_paths(tmp_path: Path) -> None:
    map_path = _workspace(
        tmp_path, map_content=_map(paths="[]", command="python scripts/missing.py")
    )

    assert _codes(impact_map_audit.audit(tmp_path, map_path)) == {
        "empty_check_paths",
        "stale_command_path",
    }


def test_audit_reports_unowned_python_and_workspace_areas(tmp_path: Path) -> None:
    map_path = _workspace(tmp_path)
    _write(tmp_path / "src/gummysnake/new_area/module.py", "VALUE = 2\n")
    _write(tmp_path / "crates/two/Cargo.toml", "[package]\nname = 'two'\n")
    _write(tmp_path / "Cargo.toml", '[workspace]\nmembers = ["crates/one", "crates/two"]\n')

    violations = impact_map_audit.audit(tmp_path, map_path)

    assert "unowned_source_path" in _codes(violations)
    assert "unowned_top_level_python_area" in _codes(violations)
    assert "unowned_workspace_crate" in _codes(violations)
    assert any(
        violation.location == "src/gummysnake/new_area/module.py" for violation in violations
    )
    assert any(violation.location == "src/gummysnake/new_area" for violation in violations)
    assert any(violation.location == "crates/two" for violation in violations)
