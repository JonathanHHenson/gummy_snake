from __future__ import annotations

import importlib.util
import sys
import tarfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "verify_distribution.py"
SDIST_ROOT = "gummy-snake-0.1.0"


def load_verify_distribution_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_distribution", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_synthetic_repository(root: Path) -> None:
    write_file(
        root / "pyproject.toml",
        """
[tool.maturin]
include = [
    "assets/samples/sonic_pi/*.flac",
    "assets/synths/README.md",
    "assets/synths/compiled/*.gss",
    "assets/fx/README.md",
    "assets/fx/compiled/*.gsfx",
]
""".lstrip(),
    )
    write_file(
        root / "crates/gummy_canvas/Cargo.toml",
        """
[package]
name = "gummy_canvas"
version = "0.1.0"

[dependencies]
gummy_ecs = { path = "../gummy_ecs" }
""".lstrip(),
    )
    write_file(
        root / "crates/gummy_ecs/Cargo.toml",
        """
[package]
name = "gummy_ecs"
version = "0.1.0"

[dependencies]
gummy_synth = { path = "../gummy_synth" }
""".lstrip(),
    )
    write_file(
        root / "crates/gummy_synth/Cargo.toml",
        """
[package]
name = "gummy_synth"
version = "0.1.0"
""".lstrip(),
    )

    write_file(root / "crates/gummy_canvas/src/lib.rs", "pub fn canvas() {}\n")
    write_file(root / "crates/gummy_ecs/src/lib.rs", "pub fn ecs() {}\n")
    write_file(root / "crates/gummy_synth/src/lib.rs", "mod oscillator;\n")
    write_file(root / "crates/gummy_synth/src/oscillator.rs", "pub fn oscillator() {}\n")
    write_file(root / "assets/samples/sonic_pi/kick.flac", "sample")
    write_file(root / "assets/synths/README.md", "synth documentation")
    write_file(root / "assets/synths/compiled/basic.gss", "compiled synth")
    write_file(root / "assets/fx/README.md", "fx documentation")
    write_file(root / "assets/fx/compiled/reverb.gsfx", "compiled fx")


def write_file(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def build_sdist(root: Path, destination: Path, excluded: set[Path] | None = None) -> None:
    excluded = excluded or set()
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.relative_to(root) in excluded:
                continue
            archive.add(path, arcname=f"{SDIST_ROOT}/{path.relative_to(root).as_posix()}")


def test_verify_distribution_accepts_complete_transitive_sources_and_assets(tmp_path: Path) -> None:
    verify_distribution = load_verify_distribution_module()
    write_synthetic_repository(tmp_path)
    sdist = tmp_path / "gummy-snake-0.1.0.tar.gz"
    build_sdist(tmp_path, sdist)

    assert verify_distribution.verify_distribution(sdist, tmp_path) == ()


def test_verify_distribution_reports_missing_transitive_rust_source(tmp_path: Path) -> None:
    verify_distribution = load_verify_distribution_module()
    write_synthetic_repository(tmp_path)
    sdist = tmp_path / "gummy-snake-0.1.0.tar.gz"
    missing_source = Path("crates/gummy_synth/src/oscillator.rs")
    build_sdist(tmp_path, sdist, {missing_source})

    assert verify_distribution.verify_distribution(sdist, tmp_path) == (missing_source,)


def test_verify_distribution_reports_missing_packaged_asset(tmp_path: Path, capsys) -> None:
    verify_distribution = load_verify_distribution_module()
    write_synthetic_repository(tmp_path)
    sdist = tmp_path / "gummy-snake-0.1.0.tar.gz"
    missing_asset = Path("assets/fx/compiled/reverb.gsfx")
    build_sdist(tmp_path, sdist, {missing_asset})

    assert verify_distribution.main([str(sdist), "--root", str(tmp_path)]) == 1
    assert missing_asset.as_posix() in capsys.readouterr().err
