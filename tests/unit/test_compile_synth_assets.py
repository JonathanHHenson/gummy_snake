from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "compile_synth_assets.py"


def load_compile_synth_assets_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compile_synth_assets", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_source_assets(root: Path) -> tuple[Path, Path]:
    synth_source_dir = root / "synth-src"
    fx_source_dir = root / "fx-src"
    synth_source_dir.mkdir()
    fx_source_dir.mkdir()
    (synth_source_dir / "tone.py").write_text(
        """from gummysnake import synth as sy

SYNTH_NAME = "tone"
DURATION = sy.duration(secs=0.1)


@sy.synth(name=SYNTH_NAME)
def tone(note: object = 60, **opts: object) -> None:
    sy.synth_input(note, **opts).layer("sine").output()


SYNTH_TRACK = tone
""",
        encoding="utf-8",
    )
    (fx_source_dir / "gain.py").write_text(
        """from gummysnake import synth as sy

NAME = "gain"
DURATION = sy.duration(secs=0.1)


@sy.fx(name=NAME)
def FX_DEFINITION(**opts: object) -> None:
    sy.fx_output(sy.fx_input().level(), **opts)
""",
        encoding="utf-8",
    )
    return synth_source_dir, fx_source_dir


def compile_fresh_assets(module: ModuleType, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    synth_source_dir, fx_source_dir = write_source_assets(tmp_path)
    synth_output_dir = tmp_path / "synth-compiled"
    fx_output_dir = tmp_path / "fx-compiled"
    module.compile_assets(
        synth_source_dir=synth_source_dir,
        fx_source_dir=fx_source_dir,
        output_dir=synth_output_dir,
        fx_output_dir=fx_output_dir,
    )
    return synth_source_dir, fx_source_dir, synth_output_dir, fx_output_dir


def asset_bytes(*directories: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(directory): path.read_bytes()
        for directory in directories
        for path in directory.rglob("*")
        if path.is_file()
    }


def test_check_assets_accepts_matching_synth_and_fx_outputs(tmp_path: Path) -> None:
    module = load_compile_synth_assets_module()
    synth_source_dir, fx_source_dir, synth_output_dir, fx_output_dir = compile_fresh_assets(
        module, tmp_path
    )

    assert (
        module.check_assets(
            synth_source_dir=synth_source_dir,
            fx_source_dir=fx_source_dir,
            output_dir=synth_output_dir,
            fx_output_dir=fx_output_dir,
        )
        == []
    )


def test_check_assets_reports_stale_byte_content(tmp_path: Path) -> None:
    module = load_compile_synth_assets_module()
    synth_source_dir, fx_source_dir, synth_output_dir, fx_output_dir = compile_fresh_assets(
        module, tmp_path
    )
    stale_asset = synth_output_dir / "tone.gss"
    stale_asset.write_bytes(b"outdated")

    differences = module.check_assets(
        synth_source_dir=synth_source_dir,
        fx_source_dir=fx_source_dir,
        output_dir=synth_output_dir,
        fx_output_dir=fx_output_dir,
    )

    assert differences == [f"stale synth compiled asset: {stale_asset}"]


def test_check_assets_reports_unexpected_compiled_asset(tmp_path: Path) -> None:
    module = load_compile_synth_assets_module()
    synth_source_dir, fx_source_dir, synth_output_dir, fx_output_dir = compile_fresh_assets(
        module, tmp_path
    )
    unexpected_asset = synth_output_dir / "obsolete.gss"
    unexpected_asset.write_bytes(b"obsolete")

    differences = module.check_assets(
        synth_source_dir=synth_source_dir,
        fx_source_dir=fx_source_dir,
        output_dir=synth_output_dir,
        fx_output_dir=fx_output_dir,
    )

    assert differences == [f"unexpected synth compiled asset: {unexpected_asset}"]


def test_check_mode_does_not_mutate_packaged_outputs_or_delete_user_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_compile_synth_assets_module()
    synth_source_dir, fx_source_dir, synth_output_dir, fx_output_dir = compile_fresh_assets(
        module, tmp_path
    )
    user_file = synth_output_dir / "keep-me.txt"
    user_file.write_text("do not delete", encoding="utf-8")
    unexpected_asset = synth_output_dir / "obsolete.gss"
    unexpected_asset.write_bytes(b"obsolete")
    before = asset_bytes(synth_output_dir, fx_output_dir)

    with pytest.raises(SystemExit) as error:
        module.main(
            [
                "--check",
                "--synth-source-dir",
                str(synth_source_dir),
                "--fx-source-dir",
                str(fx_source_dir),
                "--output-dir",
                str(synth_output_dir),
                "--fx-output-dir",
                str(fx_output_dir),
            ]
        )

    assert error.value.code == 1
    assert f"unexpected synth compiled asset: {unexpected_asset}" in capsys.readouterr().out
    assert asset_bytes(synth_output_dir, fx_output_dir) == before
    assert user_file.read_text(encoding="utf-8") == "do not delete"
