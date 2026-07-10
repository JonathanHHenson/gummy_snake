from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol


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


class _MonkeyPatch(Protocol):
    def setattr(self, target: object, name: str, value: object) -> None: ...


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_workspace(repo_root: Path, *members: str) -> None:
    member_list = ", ".join(f'"{member}"' for member in members)
    _write(repo_root / "Cargo.toml", f"[workspace]\nmembers = [{member_list}]\n")


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


def test_structure_audit_reports_obsolete_pixels_module_or_package(tmp_path: Path) -> None:
    _write(tmp_path / "src/gummysnake/pixels.py")
    _write(tmp_path / "src/gummysnake/pixels/__init__.py")

    assert "obsolete_pixels_module" in _codes(tmp_path)


def test_structure_audit_reports_obsolete_events_module_or_package(tmp_path: Path) -> None:
    _write(tmp_path / "src/gummysnake/events.py")
    _write(tmp_path / "src/gummysnake/events/__init__.py")

    assert "obsolete_events_module" in _codes(tmp_path)


def test_structure_audit_reports_stale_layout_references(tmp_path: Path) -> None:
    _write(tmp_path / "src/example/module.py", "from gummysnake.backend._canvas import helper\n")

    assert "stale_layout_reference" in _codes(tmp_path)


def test_structure_audit_reports_missing_local_markdown_link(tmp_path: Path) -> None:
    documentation = Path("docs/guide.md")
    _write(tmp_path / documentation, "Read [the missing guide](missing.md).\n")

    violations = structure_audit.audit(tmp_path)

    assert any(
        violation.code == "missing_markdown_link"
        and violation.path == documentation
        and "`missing.md`" in violation.message
        for violation in violations
    )


def test_structure_audit_reports_stale_backticked_repository_path(tmp_path: Path) -> None:
    documentation = Path("docs/guide.md")
    _write(tmp_path / documentation, "Read `src/gummysnake/missing_module.py`.\n")

    violations = structure_audit.audit(tmp_path)

    assert any(
        violation.code == "stale_repository_path"
        and violation.path == documentation
        and "`src/gummysnake/missing_module.py`" in violation.message
        for violation in violations
    )


def test_structure_audit_reports_python_support_prefix_cluster(tmp_path: Path) -> None:
    for suffix in ("assets", "context", "image", "state"):
        _write(tmp_path / f"tests/helpers/fake_canvas_{suffix}.py")

    violations = structure_audit.audit(tmp_path)

    assert any(
        violation.code == "python_support_prefix_cluster"
        and violation.path == Path("tests/helpers")
        and "`fake_canvas_`" in violation.message
        for violation in violations
    )


def test_structure_audit_reports_undocumented_rust_hub(tmp_path: Path) -> None:
    _write_workspace(tmp_path, "crates/gummy_canvas")
    _write(tmp_path / "crates/gummy_canvas/Cargo.toml", "[package]\n")
    _write(tmp_path / "crates/gummy_canvas/src/new_area.rs", "mod details;\n")
    _write(tmp_path / "crates/gummy_canvas/src/new_area/details.rs", "")

    assert "undocumented_rust_hub" in _codes(tmp_path)


def test_structure_audit_checks_gummy_ecs_rust_hubs(tmp_path: Path) -> None:
    _write_workspace(tmp_path, "crates/gummy_ecs")
    _write(tmp_path / "crates/gummy_ecs/Cargo.toml", "[package]\n")
    _write(tmp_path / "crates/gummy_ecs/src/new_area.rs", "mod details;\n")
    _write(tmp_path / "crates/gummy_ecs/src/new_area/details.rs", "")

    assert "undocumented_rust_hub" in _codes(tmp_path)


def test_structure_audit_checks_gummy_synth_rust_hubs(tmp_path: Path) -> None:
    _write_workspace(tmp_path, "crates/gummy_synth")
    _write(tmp_path / "crates/gummy_synth/Cargo.toml", "[package]\n")
    _write(tmp_path / "crates/gummy_synth/src/synth.rs", "mod details;\n")
    _write(tmp_path / "crates/gummy_synth/src/synth/details.rs", "")

    violations = structure_audit.audit(tmp_path)

    assert any(
        violation.code == "undocumented_rust_hub"
        and violation.path == Path("crates/gummy_synth/src/synth.rs")
        for violation in violations
    )


def test_structure_audit_reports_stale_documented_rust_hub(
    tmp_path: Path, monkeypatch: _MonkeyPatch
) -> None:
    documented_hub = Path("crates/gummy_synth/src/stale.rs")
    _write_workspace(tmp_path, "crates/gummy_synth")
    _write(tmp_path / "crates/gummy_synth/Cargo.toml", "[package]\n")
    _write(tmp_path / documented_hub, "mod details;\n")
    monkeypatch.setattr(structure_audit, "DOCUMENTED_RUST_HUBS", {documented_hub})

    violations = structure_audit.audit(tmp_path)

    assert any(
        violation.code == "stale_documented_rust_hub" and violation.path == documented_hub
        for violation in violations
    )


def test_structure_audit_enforces_generated_example_output_ignore(tmp_path: Path) -> None:
    (tmp_path / "examples").mkdir()
    assert "generated_example_output_policy" in _codes(tmp_path)

    _write(tmp_path / ".gitignore", "examples/output/\n")
    assert "generated_example_output_policy" not in _codes(tmp_path)
