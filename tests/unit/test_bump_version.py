from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "bump_version.py"
DEFAULT_MEMBERS = (
    "gummy_accel",
    "gummy_canvas",
    "gummy_ecs",
    "gummy_synth",
)


def load_bump_version_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bump_version", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_fake_repo(
    root: Path,
    *,
    py_version: str = "0.2.2",
    workspace_version: str = "0.2.2",
    uv_version: str | None = None,
    additional_workspace_members: tuple[str, ...] = (),
    include_uv_lock: bool = True,
) -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "gummy-snake"\nversion = "{py_version}"\n',
        encoding="utf-8",
    )
    members = (*DEFAULT_MEMBERS, *additional_workspace_members)
    workspace_members = "\n".join(f'    "crates/{member}",' for member in members)
    (root / "Cargo.toml").write_text(
        "[workspace]\n"
        f"members = [\n{workspace_members}\n]\n"
        'resolver = "2"\n\n'
        "[workspace.package]\n"
        f'version = "{workspace_version}"\n'
        'edition = "2021"\n'
        "publish = false\n",
        encoding="utf-8",
    )
    for member in members:
        manifest = root / "crates" / member / "Cargo.toml"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            "[package]\n"
            f'name = "{member}"\n'
            "version.workspace = true\n"
            "edition.workspace = true\n"
            "publish.workspace = true\n",
            encoding="utf-8",
        )
    if include_uv_lock:
        lock_version = uv_version or py_version
        (root / "uv.lock").write_text(
            f'[[package]]\nname = "gummy-snake"\nversion = "{lock_version}"\n'
            'source = { editable = "." }\n',
            encoding="utf-8",
        )


def read_managed_texts(root: Path) -> dict[Path, str]:
    paths = [root / "pyproject.toml", root / "Cargo.toml"]
    paths.extend((root / "crates" / member / "Cargo.toml") for member in DEFAULT_MEMBERS)
    lock_path = root / "uv.lock"
    if lock_path.exists():
        paths.append(lock_path)
    return {path.relative_to(root): path.read_text(encoding="utf-8") for path in paths}


def test_bump_version_accepts_exact_version_for_inherited_members(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path)

    assert module.main(["0.3.0", "--root", str(tmp_path)]) == 0

    versions = module.read_versions(tmp_path)
    assert {item.current for item in versions} == {"0.3.0"}
    assert 'version = "0.3.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.3.0"' in (tmp_path / "Cargo.toml").read_text(encoding="utf-8")
    assert 'version = "0.3.0"' in (tmp_path / "uv.lock").read_text(encoding="utf-8")
    for member in DEFAULT_MEMBERS:
        text = (tmp_path / "crates" / member / "Cargo.toml").read_text(encoding="utf-8")
        assert "version.workspace = true" in text
        assert 'version = "0.3.0"' not in text


def test_bump_version_can_increment_patch_from_workspace_version(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path, py_version="1.2.3", workspace_version="1.2.3")

    assert module.main(["patch", "--root", str(tmp_path)]) == 0

    assert {item.current for item in module.read_versions(tmp_path)} == {"1.2.4"}


def test_bump_version_dry_run_does_not_write_inherited_members(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path)
    original = read_managed_texts(tmp_path)

    assert module.main(["minor", "--dry-run", "--root", str(tmp_path)]) == 0

    assert read_managed_texts(tmp_path) == original


def test_bump_version_check_detects_python_workspace_mismatch(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path, py_version="0.2.2", workspace_version="0.2.1")

    assert module.main(["--check", "--root", str(tmp_path)]) == 1


def test_bump_version_check_detects_optional_lock_mismatch(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path, uv_version="0.2.1")

    assert module.main(["--check", "--root", str(tmp_path)]) == 1


def test_bump_version_discovers_dynamic_inherited_workspace_member(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path, additional_workspace_members=("gummy_tools",))

    assert module.main(["0.3.0", "--root", str(tmp_path)]) == 0

    dynamic_manifest = tmp_path / "crates" / "gummy_tools" / "Cargo.toml"
    assert "version.workspace = true" in dynamic_manifest.read_text(encoding="utf-8")
    effective_versions = {item.path: item.current for item in module.read_versions(tmp_path)}
    assert effective_versions[Path("crates/gummy_tools/Cargo.toml")] == "0.3.0"


def test_bump_version_writes_without_optional_uv_lock(tmp_path: Path):
    module = load_bump_version_module()
    write_fake_repo(tmp_path, include_uv_lock=False)

    assert module.main(["0.3.0", "--root", str(tmp_path)]) == 0

    assert not (tmp_path / "uv.lock").exists()
    assert {item.current for item in module.read_versions(tmp_path)} == {"0.3.0"}
