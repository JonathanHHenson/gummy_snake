from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_structure_audit() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts/structure_audit.py"
    spec = importlib.util.spec_from_file_location("structure_audit", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


structure_audit = _load_structure_audit()


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _codes(repo_root: Path) -> set[str]:
    return {violation.code for violation in structure_audit.audit(repo_root)}


def test_structure_audit_reports_private_sibling_package(tmp_path: Path) -> None:
    _write(tmp_path / "src/example/renderer.py")
    _write(tmp_path / "src/example/_renderer/__init__.py")

    assert "python_private_sibling_package" in _codes(tmp_path)


def test_structure_audit_reports_same_stem_module_package(tmp_path: Path) -> None:
    _write(tmp_path / "src/example/renderer.py")
    _write(tmp_path / "src/example/renderer/__init__.py")

    assert "python_same_stem_module_package" in _codes(tmp_path)


def test_structure_audit_reports_source_testing_package(tmp_path: Path) -> None:
    _write(tmp_path / "src/gummysnake/testing/__init__.py")

    assert "source_testing_package" in _codes(tmp_path)


def test_structure_audit_reports_stale_layout_references(tmp_path: Path) -> None:
    _write(tmp_path / "src/example/module.py", "from gummysnake.backend._canvas import helper\n")

    assert "stale_layout_reference" in _codes(tmp_path)


def test_structure_audit_reports_undocumented_rust_hub(tmp_path: Path) -> None:
    _write(tmp_path / "crates/gummy_canvas/src/new_area.rs", "mod details;\n")
    _write(tmp_path / "crates/gummy_canvas/src/new_area/details.rs", "")

    assert "undocumented_rust_hub" in _codes(tmp_path)


def test_structure_audit_enforces_generated_example_output_ignore(tmp_path: Path) -> None:
    (tmp_path / "examples").mkdir()
    assert "generated_example_output_policy" in _codes(tmp_path)

    _write(tmp_path / ".gitignore", "examples/output/\n")
    assert "generated_example_output_policy" not in _codes(tmp_path)
