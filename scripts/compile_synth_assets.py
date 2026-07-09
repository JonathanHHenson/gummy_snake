"""Compile bundled source-defined synths (.gss) and FX (.gsfx) assets."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPILED_DIR = ROOT / "assets" / "synths" / "compiled"
FX_COMPILED_DIR = ROOT / "assets" / "synths" / "fx" / "compiled"
SOURCE_PACKAGE = "gummysnake.synth.builtins"
FX_SOURCE_PACKAGE = "gummysnake.synth.fx_builtins"


def _module_name(name: str) -> str:
    return name.replace("-", "_")


def _ensure_src_on_path() -> None:
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def _delete_stale_assets(output_dir: Path, source_names: set[str], *, suffix: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_asset in output_dir.glob(f"*{suffix}"):
        if stale_asset.stem not in source_names:
            stale_asset.unlink()


def compile_synth_assets(*, output_dir: Path = COMPILED_DIR) -> list[Path]:
    _ensure_src_on_path()
    source_package = importlib.import_module(SOURCE_PACKAGE)
    source_names = set(source_package.SONIC_PI_SYNTH_KEYS)
    _delete_stale_assets(output_dir, source_names, suffix=".gss")
    written: list[Path] = []
    for name in source_package.SONIC_PI_SYNTH_KEYS:
        module = importlib.import_module(f"{SOURCE_PACKAGE}.{_module_name(name)}")
        synth_definition = module.SYNTH_TRACK
        duration = module.DURATION
        output_path = output_dir / f"{name}.gss"
        synth_definition().save(output_path, duration=duration)
        written.append(output_path)
    return written


def compile_fx_assets(*, output_dir: Path = FX_COMPILED_DIR) -> list[Path]:
    _ensure_src_on_path()
    source_package = importlib.import_module(FX_SOURCE_PACKAGE)
    source_names = set(source_package.SONIC_PI_FX_KEYS)
    _delete_stale_assets(output_dir, source_names, suffix=".gsfx")
    written: list[Path] = []
    for name in source_package.SONIC_PI_FX_KEYS:
        module = importlib.import_module(f"{FX_SOURCE_PACKAGE}.{_module_name(name)}")
        fx_definition = module.FX_DEFINITION
        duration = module.DURATION
        output_path = output_dir / f"{name}.gsfx"
        fx_definition.save(output_path, duration=duration)
        written.append(output_path)
    return written


def compile_assets(
    *,
    output_dir: Path = COMPILED_DIR,
    fx_output_dir: Path = FX_COMPILED_DIR,
) -> list[Path]:
    written = compile_synth_assets(output_dir=output_dir)
    written.extend(compile_fx_assets(output_dir=fx_output_dir))
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=COMPILED_DIR)
    parser.add_argument("--fx-output-dir", type=Path, default=FX_COMPILED_DIR)
    args = parser.parse_args()

    synths = compile_synth_assets(output_dir=args.output_dir)
    fxs = compile_fx_assets(output_dir=args.fx_output_dir)
    print(f"compiled {len(synths)} synth assets to {args.output_dir}")
    print(f"compiled {len(fxs)} FX assets to {args.fx_output_dir}")


if __name__ == "__main__":
    main()
