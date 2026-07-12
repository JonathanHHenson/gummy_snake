from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol


def _load_structure_audit() -> ModuleType:
    script_path = Path(__file__).resolve().parents[3] / "scripts/structure_audit.py"
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


def test_structure_audit_allows_an_absent_explicitly_ignored_generated_output(
    tmp_path: Path,
) -> None:
    documentation = Path("docs/guide.md")
    _write(tmp_path / documentation, "Generated examples are written to `examples/output/`.\n")
    _write(tmp_path / ".gitignore", "examples/output/\n")

    assert "stale_repository_path" not in _codes(tmp_path)


def test_structure_audit_rejects_an_absent_output_path_without_its_ignore_rule(
    tmp_path: Path,
) -> None:
    documentation = Path("docs/guide.md")
    _write(tmp_path / documentation, "Generated examples are written to `examples/output/`.\n")

    violations = structure_audit.audit(tmp_path)

    assert any(
        violation.code == "stale_repository_path"
        and violation.path == documentation
        and "`examples/output/`" in violation.message
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


def test_structure_audit_rejects_a_flat_rust_canvas_helper_cluster(tmp_path: Path) -> None:
    for suffix in ("assets", "context", "modules", "state"):
        _write(tmp_path / f"tests/helpers/rust_canvas_{suffix}.py")

    assert "python_support_prefix_cluster" in _codes(tmp_path)


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


def test_structure_audit_ignores_virtual_environment_markdown(tmp_path: Path) -> None:
    _write(tmp_path / ".venv/third_party/README.md", "Read [missing](missing.md).\n")

    assert "missing_markdown_link" not in _codes(tmp_path)


def test_structure_audit_reports_maturin_include_glob_without_matches(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.maturin]\ninclude = ["assets/present.txt", "assets/missing/*.gss"]\n',
    )
    _write(tmp_path / "assets/present.txt")

    violations = structure_audit.audit(tmp_path)

    assert any(
        violation.code == "maturin_include_no_matches"
        and violation.path == Path("pyproject.toml")
        and "assets/missing/*.gss" in violation.message
        for violation in violations
    )


def test_structure_audit_reports_cargo_path_dependency_outside_repo(tmp_path: Path) -> None:
    manifest = Path("crates/gummy_accel/Cargo.toml")
    _write(
        tmp_path / manifest,
        '[package]\nname = "gummy_accel"\n[dependencies]\nother = { path = "../../../outside" }\n',
    )

    violations = structure_audit.audit(tmp_path)

    assert any(
        violation.code == "cargo_path_dependency_outside_repo" and violation.path == manifest
        for violation in violations
    )


def test_structure_audit_reports_disallowed_local_cargo_dependency(tmp_path: Path) -> None:
    manifest = Path("crates/gummy_accel/Cargo.toml")
    _write(
        tmp_path / manifest,
        '[package]\nname = "gummy_accel"\n[dependencies]\ngummy_ecs = { path = "../gummy_ecs" }\n',
    )
    _write(tmp_path / "crates/gummy_ecs/Cargo.toml", '[package]\nname = "gummy_ecs"\n')

    violations = structure_audit.audit(tmp_path)

    assert any(
        violation.code == "cargo_local_dependency_not_allowed"
        and violation.path == manifest
        and "gummy_accel" in violation.message
        for violation in violations
    )


def test_structure_audit_reports_missing_makefile_and_workflow_recipe_paths(tmp_path: Path) -> None:
    _write(tmp_path / "scripts/present.py")
    _write(
        tmp_path / "Makefile",
        "check:\n\tpython scripts/present.py && python scripts/missing.py\n",
    )
    workflow = Path(".github/workflows/check.yml")
    _write(
        tmp_path / workflow,
        "jobs:\n  check:\n    steps:\n      - run: |\n          python examples/missing.py\n",
    )

    violations = structure_audit.audit(tmp_path)

    missing_paths = {
        (violation.path, violation.message)
        for violation in violations
        if violation.code == "missing_recipe_path"
    }
    assert (Path("Makefile"), "recipe path `scripts/missing.py` does not exist") in missing_paths
    assert (workflow, "recipe path `examples/missing.py` does not exist") in missing_paths


def test_structure_audit_requires_all_generated_artifact_ignore_entries(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "examples/output/\n")

    violations = structure_audit.audit(tmp_path)

    missing_entries = {
        violation.message
        for violation in violations
        if violation.code == "generated_artifact_ignore_policy"
    }
    assert "add `target/` to ignore generated artifacts and caches" in missing_entries
    assert "add `.pytest_cache/` to ignore generated artifacts and caches" in missing_entries


def test_structure_audit_reports_only_tracked_generated_artifacts(
    tmp_path: Path, monkeypatch: _MonkeyPatch
) -> None:
    monkeypatch.setattr(
        structure_audit,
        "_tracked_paths",
        lambda repo_root: [
            Path("assets/samples/intentional.flac"),
            Path("src/gummysnake/module.py"),
            Path(".pytest_cache/state"),
            Path("src/gummysnake/rust/_canvas.so"),
            Path("examples/output/render.png"),
            Path("coverage.xml"),
        ],
    )

    violations = structure_audit.audit(tmp_path)

    tracked_paths = {
        violation.path for violation in violations if violation.code == "tracked_generated_artifact"
    }
    assert tracked_paths == {
        Path(".pytest_cache/state"),
        Path("src/gummysnake/rust/_canvas.so"),
        Path("examples/output/render.png"),
        Path("coverage.xml"),
    }
