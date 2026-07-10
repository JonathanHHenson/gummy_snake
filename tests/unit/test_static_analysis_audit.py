from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "static_analysis_audit.py"


def _load_audit() -> ModuleType:
    spec = importlib.util.spec_from_file_location("static_analysis_audit", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


static_analysis_audit = _load_audit()


class _Violation(Protocol):
    code: str


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _manifest(*, inline: str = "", ruff: str = "", type_checks: str = "") -> str:
    return f"""[manifest]
version = 1
roots = ["src"]
{type_checks}
{ruff}
{inline}
"""


def _workspace(tmp_path: Path, manifest: str) -> Path:
    _write(tmp_path / "pyproject.toml", "[tool.mypy]\n[tool.basedpyright]\n[tool.ruff.lint]\n")
    _write(tmp_path / "src/package/module.py", "VALUE = 1\n")
    manifest_path = tmp_path / "static_analysis_exceptions.toml"
    _write(manifest_path, manifest)
    return manifest_path


def _codes(violations: list[_Violation]) -> set[str]:
    return {violation.code for violation in violations}


def test_repository_static_analysis_manifest_is_current() -> None:
    assert static_analysis_audit.audit(ROOT) == []


def test_audit_rejects_unowned_inline_suppression(tmp_path: Path) -> None:
    manifest_path = _workspace(tmp_path, _manifest())
    _write(tmp_path / "src/package/module.py", "VALUE = 1  # noqa: F401\n")

    assert "unowned_inline_suppression" in _codes(
        static_analysis_audit.audit(tmp_path, manifest_path)
    )


def test_audit_rejects_broad_undefined_name_ruff_ignore(tmp_path: Path) -> None:
    ruff = """
[[ruff_ignores]]
pattern = "src/package/*.py"
codes = ["F821"]
owner = "Fixture owner"
removal_pbi = "PBI 008"
reason = "Fixture only."
checks = ["pytest tests/unit/test_static_analysis_audit.py"]
"""
    manifest_path = _workspace(tmp_path, _manifest(ruff=ruff))
    _write(
        tmp_path / "pyproject.toml",
        """[tool.mypy]
[tool.basedpyright]
[tool.ruff.lint.per-file-ignores]
"src/package/*.py" = ["F821"]
""",
    )

    assert "broad_undefined_name_ignore" in _codes(
        static_analysis_audit.audit(tmp_path, manifest_path)
    )


def test_audit_requires_exact_type_checker_exceptions(tmp_path: Path) -> None:
    type_checks = """
[[type_check_exceptions]]
tool = "mypy"
path = "src/package/*.py"
owner = "Fixture owner"
removal_pbi = "PBI 008"
reason = "Fixture only."
checks = ["pytest tests/unit/test_static_analysis_audit.py"]
"""
    manifest_path = _workspace(tmp_path, _manifest(type_checks=type_checks))
    _write(
        tmp_path / "pyproject.toml",
        '[tool.mypy]\nexclude = ["src/package/*.py"]\n[tool.basedpyright]\n[tool.ruff.lint]\n',
    )

    assert "broad_type_check_exception" in _codes(
        static_analysis_audit.audit(tmp_path, manifest_path)
    )
