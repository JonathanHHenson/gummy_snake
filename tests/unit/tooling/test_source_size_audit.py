from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol


class MonkeyPatch(Protocol):
    def chdir(self, path: str | Path) -> None: ...

    def setattr(self, target: object, name: str, value: object) -> None: ...


class CapturedOutput(Protocol):
    out: str


class CaptureFixture(Protocol):
    def readouterr(self) -> CapturedOutput: ...


def _load_source_size_audit() -> ModuleType:
    script_path = Path(__file__).resolve().parents[3] / "scripts/source_size_audit.py"
    spec = importlib.util.spec_from_file_location("source_size_audit", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


source_size_audit = _load_source_size_audit()


def _write(path: Path, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("let value = 0;\n" * lines)


def _workspace(root: Path, members: tuple[str, ...]) -> None:
    quoted_members = ", ".join(f'"{member}"' for member in members)
    (root / "Cargo.toml").write_text(f"[workspace]\nmembers = [{quoted_members}]\n")


def test_default_roots_discovers_all_rust_workspace_members(tmp_path: Path) -> None:
    members = (
        "crates/gummy_canvas",
        "crates/gummy_ecs",
        "crates/gummy_synth",
        "crates/gummy_accel",
    )
    _workspace(tmp_path, members)
    for member in members:
        (tmp_path / member).mkdir(parents=True)

    sorted_members = tuple(sorted(members))
    assert source_size_audit.rust_source_roots(tmp_path) == tuple(
        tmp_path / member / "src" for member in sorted_members
    )
    assert source_size_audit.default_roots(tmp_path) == (
        tmp_path / "src",
        *(tmp_path / member / "src" for member in sorted_members),
        tmp_path / "tests",
        tmp_path / "examples",
    )


def test_category_for_classifies_workspace_sources_as_production(tmp_path: Path) -> None:
    members = (
        "crates/gummy_canvas",
        "crates/gummy_ecs",
        "crates/gummy_synth",
        "crates/gummy_accel",
    )
    _workspace(tmp_path, members)
    for member in members:
        (tmp_path / member).mkdir(parents=True)
    production_roots = source_size_audit.production_roots(tmp_path)

    for member in members:
        path = tmp_path / member / "src" / "module.rs"
        _write(path, 1)
        assert (
            source_size_audit.category_for(
                path,
                repo_root=tmp_path,
                production_source_roots=production_roots,
            )
            == "production"
        )

    test_path = tmp_path / "tests" / "unit" / "test_module.py"
    _write(test_path, 1)
    assert source_size_audit.category_for(test_path, repo_root=tmp_path) == "test/example"


def test_check_succeeds_for_a_file_at_its_reviewed_baseline(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    member = "crates/gummy_ecs"
    _workspace(tmp_path, (member,))
    baseline_path = tmp_path / member / "src" / "existing.rs"
    _write(baseline_path, 501)
    limit = source_size_audit.ReviewedLimit(501, "reviewed test baseline")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        source_size_audit,
        "REVIEWED_PRODUCTION_LIMITS",
        {Path(member) / "src" / "existing.rs": limit},
    )
    monkeypatch.setattr(source_size_audit, "BINDING_EXCEPTION_LIMITS", {})

    assert source_size_audit.main(["--check"]) == 0


def test_check_fails_for_new_and_enlarged_unapproved_production_files(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture
) -> None:
    member = "crates/gummy_ecs"
    _workspace(tmp_path, (member,))
    _write(tmp_path / member / "src" / "existing.rs", 502)
    _write(tmp_path / member / "src" / "new.rs", 501)
    limit = source_size_audit.ReviewedLimit(501, "reviewed test baseline")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        source_size_audit,
        "REVIEWED_PRODUCTION_LIMITS",
        {Path(member) / "src" / "existing.rs": limit},
    )
    monkeypatch.setattr(source_size_audit, "BINDING_EXCEPTION_LIMITS", {})

    assert source_size_audit.main(["--check"]) == 1
    new_file_reason = "new production file over the 500-line enforcement threshold"
    assert capsys.readouterr().out.splitlines() == [
        "SOURCE_SIZE_CHECK FAILED",
        " 502 limit 501        crates/gummy_ecs/src/existing.rs  # reviewed test baseline",
        f" 501 limit unapproved crates/gummy_ecs/src/new.rs  # {new_file_reason}",
    ]
