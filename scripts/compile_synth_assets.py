"""Compile bundled source-defined synths (.gss) and FX (.gsfx) assets."""

from __future__ import annotations

import argparse
import ast
import contextlib
import importlib.util
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SYNTH_SOURCE_DIR = ROOT / "assets" / "synths" / "src"
FX_SOURCE_DIR = ROOT / "assets" / "fx" / "src"
COMPILED_DIR = ROOT / "assets" / "synths" / "compiled"
FX_COMPILED_DIR = ROOT / "assets" / "fx" / "compiled"


def _ensure_import_paths(*paths: Path) -> None:
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    for path in reversed(paths):
        raw = str(path)
        if raw not in sys.path:
            sys.path.insert(0, raw)


def _source_files(source_dir: Path) -> tuple[Path, ...]:
    if not source_dir.exists():
        raise FileNotFoundError(f"source asset directory does not exist: {source_dir}")
    return tuple(
        sorted(
            path
            for path in source_dir.glob("*.py")
            if path.name != "__init__.py" and not path.name.startswith("_")
        )
    )


@contextlib.contextmanager
def _deterministic_node_ids() -> Iterator[None]:
    """Compile source plans from a stable node-ID sequence without affecting callers."""

    from gummysnake.synth.synth_runtime.composition import builder_context

    previous_node_counter = builder_context._NODE_COUNTER
    builder_context._NODE_COUNTER = 0
    try:
        yield
    finally:
        builder_context._NODE_COUNTER = previous_node_counter


def _load_source_module(path: Path, *, namespace: str) -> ModuleType:
    module_name = f"_gummysnake_asset_{namespace}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not create module spec for asset source {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _delete_stale_assets(output_dir: Path, source_names: set[str], *, suffix: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_asset in output_dir.glob(f"*{suffix}"):
        if stale_asset.stem not in source_names:
            stale_asset.unlink()


def _opts_pop_candidates(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(), filename=str(path))
    candidates: dict[str, object] = {}

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> Any:  # noqa: N802 - ast visitor API
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "pop"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "opts"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                default: object = None
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    default = node.args[1].value
                candidates.setdefault(node.args[0].value, default)
            self.generic_visit(node)

    Visitor().visit(tree)
    return candidates


def _probe_value(default: object) -> object:
    if isinstance(default, bool):
        return not default
    if isinstance(default, int | float):
        return float(default) + 1.234 if float(default) != 0.0 else 1.234
    if isinstance(default, str):
        return f"{default}__gummy_probe__"
    return 1.234


def _canonical_template_payload(value: object) -> object:
    """Strip generated identity fields before template-parameter diffing."""

    if isinstance(value, Mapping):
        return {
            key: _canonical_template_payload(item)
            for key, item in value.items()
            if str(key) not in {"id", "instance", "node_id", "target_id", "target_instance"}
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_canonical_template_payload(item) for item in value]
    return value


def _diff_paths(left: object, right: object, prefix: tuple[object, ...] = ()) -> list[list[object]]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        paths: list[list[object]] = []
        for key in sorted(set(left) | set(right), key=str):
            if key not in left or key not in right:
                paths.append([*prefix, key])
            else:
                paths.extend(_diff_paths(left[key], right[key], (*prefix, key)))
        return paths
    if (
        isinstance(left, Sequence)
        and isinstance(right, Sequence)
        and not isinstance(left, str | bytes | bytearray)
        and not isinstance(right, str | bytes | bytearray)
    ):
        paths = []
        max_len = max(len(left), len(right))
        for index in range(max_len):
            if index >= len(left) or index >= len(right):
                paths.append([*prefix, index])
            else:
                paths.extend(_diff_paths(left[index], right[index], (*prefix, index)))
        return paths
    return [] if left == right else [list(prefix)]


def _template_parameter_metadata(
    *,
    source_path: Path,
    build_plan: Any,
    duration: object,
) -> dict[str, object]:
    parameters: list[dict[str, object]] = []
    candidates = _opts_pop_candidates(source_path)
    if not candidates:
        return {}
    default_plan = build_plan({}).physical_plan(duration).to_dict()
    for name, default in sorted(candidates.items()):
        probe = _probe_value(default)
        variant_plan = build_plan({name: probe}).physical_plan(duration).to_dict()
        paths = _diff_paths(
            _canonical_template_payload(default_plan.get("events", ())),
            _canonical_template_payload(variant_plan.get("events", ())),
            ("events",),
        )
        paths.extend(
            _diff_paths(
                _canonical_template_payload(default_plan.get("controls", ())),
                _canonical_template_payload(variant_plan.get("controls", ())),
                ("controls",),
            )
        )
        if paths:
            parameters.append({"name": name, "paths": paths})
    return {"template_parameters": parameters} if parameters else {}


def compile_synth_assets(
    *,
    source_dir: Path = SYNTH_SOURCE_DIR,
    output_dir: Path = COMPILED_DIR,
) -> list[Path]:
    _ensure_import_paths(source_dir)
    sys.modules.pop("_common", None)
    modules = [_load_source_module(path, namespace="synth") for path in _source_files(source_dir)]
    source_names = {str(module.SYNTH_NAME) for module in modules}
    _delete_stale_assets(output_dir, source_names, suffix=".gss")
    written: list[Path] = []
    for module in modules:
        synth_name = str(module.SYNTH_NAME)
        synth_definition = module.SYNTH_TRACK
        duration = module.DURATION
        source_path = Path(module.__file__ or source_dir / f"{module.__name__}.py")
        metadata = _template_parameter_metadata(
            source_path=source_path,
            build_plan=lambda opts, definition=synth_definition: definition(**opts),
            duration=duration,
        )
        output_path = output_dir / f"{synth_name}.gss"
        synth_definition().physical_plan(duration).save(output_path, metadata=metadata)
        written.append(output_path)
    return written


def compile_fx_assets(
    *,
    source_dir: Path = FX_SOURCE_DIR,
    output_dir: Path = FX_COMPILED_DIR,
) -> list[Path]:
    _ensure_import_paths(source_dir)
    sys.modules.pop("_common", None)
    modules = [_load_source_module(path, namespace="fx") for path in _source_files(source_dir)]
    source_names = {str(module.NAME) for module in modules}
    _delete_stale_assets(output_dir, source_names, suffix=".gsfx")
    written: list[Path] = []
    for module in modules:
        fx_name = str(module.NAME)
        fx_definition = module.FX_DEFINITION
        duration = module.DURATION
        output_path = output_dir / f"{fx_name}.gsfx"
        fx_definition.physical_plan(duration).save(output_path)
        written.append(output_path)
    return written


def compile_assets(
    *,
    synth_source_dir: Path = SYNTH_SOURCE_DIR,
    fx_source_dir: Path = FX_SOURCE_DIR,
    output_dir: Path = COMPILED_DIR,
    fx_output_dir: Path = FX_COMPILED_DIR,
) -> list[Path]:
    with _deterministic_node_ids():
        written = compile_synth_assets(source_dir=synth_source_dir, output_dir=output_dir)
        written.extend(compile_fx_assets(source_dir=fx_source_dir, output_dir=fx_output_dir))
        return written


def _compiled_asset_paths(output_dir: Path, *, suffix: str) -> dict[str, Path]:
    if not output_dir.exists():
        return {}
    return {path.name: path for path in sorted(output_dir.glob(f"*{suffix}")) if path.is_file()}


def _asset_freshness_differences(
    *,
    generated_dir: Path,
    packaged_dir: Path,
    suffix: str,
    asset_kind: str,
) -> list[str]:
    generated = _compiled_asset_paths(generated_dir, suffix=suffix)
    packaged = _compiled_asset_paths(packaged_dir, suffix=suffix)
    differences: list[str] = []

    for name in sorted(set(generated) - set(packaged)):
        differences.append(f"missing {asset_kind} compiled asset: {packaged_dir / name}")
    for name in sorted(set(packaged) - set(generated)):
        differences.append(f"unexpected {asset_kind} compiled asset: {packaged[name]}")
    for name in sorted(set(generated) & set(packaged)):
        if generated[name].read_bytes() != packaged[name].read_bytes():
            differences.append(f"stale {asset_kind} compiled asset: {packaged[name]}")
    return differences


def check_assets(
    *,
    synth_source_dir: Path = SYNTH_SOURCE_DIR,
    fx_source_dir: Path = FX_SOURCE_DIR,
    output_dir: Path = COMPILED_DIR,
    fx_output_dir: Path = FX_COMPILED_DIR,
) -> list[str]:
    """Return packaged synth/FX asset freshness differences without modifying them."""

    with tempfile.TemporaryDirectory(prefix="gummysnake-synth-assets-") as temporary_dir:
        temporary_output_dir = Path(temporary_dir)
        generated_synth_dir = temporary_output_dir / "synths"
        generated_fx_dir = temporary_output_dir / "fx"
        compile_assets(
            synth_source_dir=synth_source_dir,
            fx_source_dir=fx_source_dir,
            output_dir=generated_synth_dir,
            fx_output_dir=generated_fx_dir,
        )
        return [
            *_asset_freshness_differences(
                generated_dir=generated_synth_dir,
                packaged_dir=output_dir,
                suffix=".gss",
                asset_kind="synth",
            ),
            *_asset_freshness_differences(
                generated_dir=generated_fx_dir,
                packaged_dir=fx_output_dir,
                suffix=".gsfx",
                asset_kind="FX",
            ),
        ]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synth-source-dir", type=Path, default=SYNTH_SOURCE_DIR)
    parser.add_argument("--fx-source-dir", type=Path, default=FX_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=COMPILED_DIR)
    parser.add_argument("--fx-output-dir", type=Path, default=FX_COMPILED_DIR)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify compiled assets are current without modifying packaged outputs",
    )
    args = parser.parse_args(argv)

    if args.check:
        differences = check_assets(
            synth_source_dir=args.synth_source_dir,
            fx_source_dir=args.fx_source_dir,
            output_dir=args.output_dir,
            fx_output_dir=args.fx_output_dir,
        )
        if differences:
            print("compiled synth/FX assets are out of date:")
            for difference in differences:
                print(f"  {difference}")
            raise SystemExit(1)
        print("compiled synth/FX assets are current")
        return

    assets = compile_assets(
        synth_source_dir=args.synth_source_dir,
        fx_source_dir=args.fx_source_dir,
        output_dir=args.output_dir,
        fx_output_dir=args.fx_output_dir,
    )
    synths = [path for path in assets if path.suffix == ".gss"]
    fxs = [path for path in assets if path.suffix == ".gsfx"]
    print(f"compiled {len(synths)} synth assets to {args.output_dir}")
    print(f"compiled {len(fxs)} FX assets to {args.fx_output_dir}")


if __name__ == "__main__":
    main()
