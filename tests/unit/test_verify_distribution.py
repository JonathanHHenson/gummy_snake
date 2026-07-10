from __future__ import annotations

import importlib.util
import sys
import tarfile
import zipfile
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


def build_wheel(path: Path, extension: str) -> None:
    """Write a synthetic wheel archive with the required native interface files."""

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("gummysnake/py.typed", "")
        archive.writestr("gummysnake/rust/_canvas.pyi", "def canvas() -> None: ...\n")
        archive.writestr("gummysnake/rust/_accelerated.pyi", "def accelerated() -> None: ...\n")
        archive.writestr(f"gummysnake/rust/{extension}.so", "native")


def test_wheel_contract_requires_typed_marker_native_extension_and_stubs(tmp_path: Path) -> None:
    verify_distribution = load_verify_distribution_module()
    wheel = tmp_path / "gummy_snake-0.1.0.whl"
    build_wheel(wheel, "_canvas")

    assert (
        verify_distribution.wheel_contract_missing_paths(wheel, verify_distribution.CANVAS_MODULE)
        == ()
    )

    # Omit the marker in a fresh wheel to prove the failure is exact.
    missing_marker_wheel = tmp_path / "missing-marker.whl"
    with zipfile.ZipFile(missing_marker_wheel, "w") as archive:
        archive.writestr("gummysnake/rust/_canvas.pyi", "")
        archive.writestr("gummysnake/rust/_accelerated.pyi", "")
        archive.writestr("gummysnake/rust/_canvas.so", "native")
    assert verify_distribution.wheel_contract_missing_paths(
        missing_marker_wheel, verify_distribution.CANVAS_MODULE
    ) == ("gummysnake/py.typed",)


def test_extension_surface_drift_detects_missing_symbols_and_signature_changes() -> None:
    verify_distribution = load_verify_distribution_module()
    stub = """
def present(value: int = 1) -> None: ...
def missing() -> None: ...
class Present: ...
class Missing: ...
"""
    runtime = {
        "functions": {
            "present": [
                {
                    "name": "value",
                    "kind": "POSITIONAL_OR_KEYWORD",
                    "has_default": True,
                    "default": 2,
                }
            ],
            "extra": [],
        },
        "classes": ["Present", "Extra"],
    }

    assert verify_distribution.extension_surface_drift(stub, runtime) == (
        "stub declares missing extension function: missing",
        "extension function is missing from stub: extra",
        "signature mismatch for present: stub "
        "(('value', 'POSITIONAL_OR_KEYWORD', True, 1),) != extension "
        "(('value', 'POSITIONAL_OR_KEYWORD', True, 2),)",
        "stub declares missing extension class: Missing",
        "extension class is missing from stub: Extra",
    )


def test_installed_wheel_contract_runs_canvas_and_optional_acceleration_checks(
    tmp_path: Path, monkeypatch
) -> None:
    verify_distribution = load_verify_distribution_module()
    canvas_wheel = tmp_path / "canvas.whl"
    accelerated_wheel = tmp_path / "accelerated.whl"
    build_wheel(canvas_wheel, "_canvas")
    build_wheel(accelerated_wheel, "_accelerated")
    checked: list[tuple[Path, str]] = []
    consumer_wheels: list[Path] = []

    monkeypatch.setattr(
        verify_distribution,
        "_verify_extension_surface",
        lambda wheel, module: checked.append((wheel, module)),
    )
    monkeypatch.setattr(
        verify_distribution,
        "_run_isolated_consumer_checks",
        lambda wheel: consumer_wheels.append(wheel),
    )

    verify_distribution.verify_installed_wheel(canvas_wheel, accelerated_wheel=accelerated_wheel)

    assert checked == [
        (canvas_wheel.resolve(), verify_distribution.CANVAS_MODULE),
        (accelerated_wheel.resolve(), verify_distribution.ACCELERATED_MODULE),
    ]
    assert consumer_wheels == [canvas_wheel.resolve()]
