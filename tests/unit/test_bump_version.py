from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "bump_version.py"


def load_bump_version_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bump_version", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fake_repo(root: Path, *, py_version: str = "0.2.2", crate_version: str = "0.2.2") -> None:
    (root / "crates" / "gummy_canvas").mkdir(parents=True)
    (root / "crates" / "gummy_accel").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "gummy-snake"\nversion = "{py_version}"\n',
        encoding="utf-8",
    )
    for crate in ("gummy_canvas", "gummy_accel"):
        (root / "crates" / crate / "Cargo.toml").write_text(
            f'[package]\nname = "{crate}"\nversion = "{crate_version}"\n',
            encoding="utf-8",
        )
    (root / "uv.lock").write_text(
        f'[[package]]\nname = "gummy-snake"\nversion = "{py_version}"\n'
        'source = { editable = "." }\n',
        encoding="utf-8",
    )


def read_texts(root: Path) -> tuple[str, str, str, str]:
    return (
        (root / "pyproject.toml").read_text(encoding="utf-8"),
        (root / "crates" / "gummy_canvas" / "Cargo.toml").read_text(encoding="utf-8"),
        (root / "crates" / "gummy_accel" / "Cargo.toml").read_text(encoding="utf-8"),
        (root / "uv.lock").read_text(encoding="utf-8"),
    )


def test_bump_version_accepts_exact_version(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path)

    assert module.main(["0.3.0", "--root", str(tmp_path)]) == 0

    for text in read_texts(tmp_path):
        assert 'version = "0.3.0"' in text


def test_bump_version_can_increment_patch(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path, py_version="1.2.3", crate_version="1.2.3")

    assert module.main(["patch", "--root", str(tmp_path)]) == 0

    for text in read_texts(tmp_path):
        assert 'version = "1.2.4"' in text


def test_bump_version_dry_run_does_not_write(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path)

    assert module.main(["minor", "--dry-run", "--root", str(tmp_path)]) == 0

    for text in read_texts(tmp_path):
        assert 'version = "0.2.2"' in text


def test_bump_version_check_detects_mismatched_versions(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path, py_version="0.2.2", crate_version="0.2.1")

    assert module.main(["--check", "--root", str(tmp_path)]) == 1
