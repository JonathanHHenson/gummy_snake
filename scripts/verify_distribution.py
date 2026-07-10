#!/usr/bin/env python3
"""Verify source- and wheel-distribution release contracts.

The source-distribution contract follows every local Cargo ``path`` dependency
from ``gummy_canvas`` and verifies Maturin-included assets.  The wheel contract
requires the mandatory canvas extension, typed-package marker, native stubs,
and package assets.  It then installs the wheel in an isolated ``uv``
environment to compare native symbols and signatures with the shipped stubs and
to type-check and run a small consumer without access to the checkout.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import tomllib
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath

CANVAS_MANIFEST = Path("crates/gummy_canvas/Cargo.toml")
PYPROJECT = Path("pyproject.toml")
DEPENDENCY_SECTIONS = ("dependencies", "build-dependencies")
PACKAGE_ROOT = PurePosixPath("gummysnake")
RUST_PACKAGE_ROOT = PACKAGE_ROOT / "rust"
CANVAS_MODULE = "gummysnake.rust._canvas"
ACCELERATED_MODULE = "gummysnake.rust._accelerated"
NATIVE_SUFFIXES = {".so", ".pyd", ".dylib"}
REQUIRED_WHEEL_PATHS = (
    PACKAGE_ROOT / "py.typed",
    RUST_PACKAGE_ROOT / "_canvas.pyi",
    RUST_PACKAGE_ROOT / "_accelerated.pyi",
)
_NO_DEFAULT = object()


class DistributionConfigurationError(RuntimeError):
    """Raised when verification inputs cannot define an unambiguous contract."""


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse source- and wheel-distribution verification arguments."""

    parser = argparse.ArgumentParser(
        description="Verify Gummy Snake source and installed-wheel release contracts."
    )
    parser.add_argument(
        "sdist",
        nargs="?",
        type=Path,
        help="Optional source-distribution tar.gz file to verify.",
    )
    parser.add_argument(
        "--wheel",
        type=Path,
        help="Canvas-runtime wheel to verify as an isolated installed consumer.",
    )
    parser.add_argument(
        "--accelerated-wheel",
        type=Path,
        help="Optional gummy_accel wheel whose native stub is checked separately.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Checkout used to determine source-distribution inputs (default: repository root).",
    )
    args = parser.parse_args(argv)
    if args.sdist is None and args.wheel is None and args.accelerated_wheel is None:
        parser.error("provide an sdist, --wheel, or --accelerated-wheel")
    if args.accelerated_wheel is not None and args.wheel is None:
        parser.error("--accelerated-wheel requires --wheel so the installed-wheel contract runs")
    return args


def main(argv: list[str] | None = None) -> int:
    """Run requested verification and return a process-compatible status code."""

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.sdist is not None:
            missing = verify_distribution(args.sdist, args.root)
            if missing:
                _print_missing("Source distribution", missing)
                return 1
            print("Source distribution contains all required Cargo sources and Maturin assets.")
        if args.wheel is not None:
            verify_installed_wheel(args.wheel, accelerated_wheel=args.accelerated_wheel)
            print("Installed-wheel contract passed.")
    except (DistributionConfigurationError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as error:
        print(
            f"error: isolated wheel verification failed with exit code {error.returncode}",
            file=sys.stderr,
        )
        return error.returncode or 1

    return 0


def verify_distribution(sdist_path: Path, project_root: Path | None = None) -> tuple[Path, ...]:
    """Return project-relative paths required by *sdist_path* but absent from it."""

    root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    required = required_distribution_paths(root)
    archive_files, archive_root = sdist_file_paths(sdist_path)
    return tuple(
        path for path in required if _archive_member_path(archive_root, path) not in archive_files
    )


def verify_installed_wheel(wheel_path: Path, *, accelerated_wheel: Path | None = None) -> None:
    """Verify a built canvas wheel and exercise it outside the source checkout.

    ``gummysnake/py.typed`` is deliberately part of this contract: Gummy Snake
    ships typed Python and native-stub interfaces.  The optional acceleration
    extension is packaged independently, so its native surface is checked only
    when its separately built wheel is supplied.
    """

    wheel = wheel_path.resolve()
    missing = wheel_contract_missing_paths(wheel, CANVAS_MODULE)
    if missing:
        raise DistributionConfigurationError(
            "Canvas wheel is missing required paths:\n" + "\n".join(f"  {path}" for path in missing)
        )
    _verify_extension_surface(wheel, CANVAS_MODULE)
    _run_isolated_consumer_checks(wheel)

    if accelerated_wheel is not None:
        acceleration = accelerated_wheel.resolve()
        missing = wheel_contract_missing_paths(acceleration, ACCELERATED_MODULE)
        if missing:
            raise DistributionConfigurationError(
                "Acceleration wheel is missing required paths:\n"
                + "\n".join(f"  {path}" for path in missing)
            )
        _verify_extension_surface(acceleration, ACCELERATED_MODULE)


def wheel_contract_missing_paths(wheel_path: Path, module_name: str) -> tuple[str, ...]:
    """Return required typed/native wheel members absent from *wheel_path*."""

    if not wheel_path.is_file():
        raise DistributionConfigurationError(f"Wheel does not exist: {wheel_path}")
    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())

    required = (
        list(REQUIRED_WHEEL_PATHS)
        if module_name == CANVAS_MODULE
        else [PACKAGE_ROOT / "py.typed", RUST_PACKAGE_ROOT / "_accelerated.pyi"]
    )
    extension_stem = module_name.rsplit(".", maxsplit=1)[-1]
    extension_prefix = f"{RUST_PACKAGE_ROOT.as_posix()}/{extension_stem}."
    if not any(
        name.startswith(extension_prefix) and Path(name).suffix in NATIVE_SUFFIXES for name in names
    ):
        required.append(PurePosixPath(f"{extension_prefix}<native extension>"))
    return tuple(path.as_posix() for path in required if path.as_posix() not in names)


def required_distribution_paths(project_root: Path) -> tuple[Path, ...]:
    """Return all project-relative files that must be packaged in an sdist."""

    root = project_root.resolve()
    pyproject = root / PYPROJECT
    canvas_manifest = root / CANVAS_MANIFEST
    if not pyproject.is_file():
        raise DistributionConfigurationError(f"Missing project manifest: {PYPROJECT}")
    if not canvas_manifest.is_file():
        raise DistributionConfigurationError(f"Missing canvas Cargo manifest: {CANVAS_MANIFEST}")

    required: set[Path] = {PYPROJECT}
    for crate_directory in local_cargo_crates(canvas_manifest, root):
        required.add(_relative_to_root(crate_directory / "Cargo.toml", root))
        required.update(_crate_source_paths(crate_directory, root))
    required.update(maturin_include_paths(pyproject, root))
    return tuple(sorted(required, key=lambda path: path.as_posix()))


def local_cargo_crates(canvas_manifest: Path, project_root: Path) -> tuple[Path, ...]:
    """Return canvas and every recursive local Cargo path dependency directory."""

    root = project_root.resolve()
    pending = [canvas_manifest.resolve()]
    visited: set[Path] = set()
    crates: list[Path] = []

    while pending:
        manifest = pending.pop()
        crate_directory = manifest.parent
        if crate_directory in visited:
            continue
        if not manifest.is_file():
            relative = _relative_to_root(manifest, root)
            raise DistributionConfigurationError(f"Missing Cargo manifest: {relative}")

        visited.add(crate_directory)
        _relative_to_root(crate_directory, root)
        crates.append(crate_directory)
        for dependency_path in cargo_path_dependencies(manifest):
            dependency_manifest = (crate_directory / dependency_path / "Cargo.toml").resolve()
            _relative_to_root(dependency_manifest, root)
            pending.append(dependency_manifest)

    return tuple(sorted(crates, key=lambda path: _relative_to_root(path, root).as_posix()))


def cargo_path_dependencies(manifest_path: Path) -> tuple[Path, ...]:
    """Read local Cargo dependency paths from normal and build dependency tables."""

    manifest = _read_toml(manifest_path)
    paths: set[Path] = set()
    for dependencies in _dependency_tables(manifest):
        for specification in dependencies.values():
            if not isinstance(specification, Mapping):
                continue
            path = specification.get("path")
            if isinstance(path, str):
                dependency_path = Path(path)
                if dependency_path.is_absolute():
                    raise DistributionConfigurationError(
                        f"Cargo path dependencies must be relative: {manifest_path}: {path}"
                    )
                paths.add(dependency_path)
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def maturin_include_paths(pyproject_path: Path, project_root: Path) -> tuple[Path, ...]:
    """Expand the current ``tool.maturin.include`` patterns to packaged files."""

    document = _read_toml(pyproject_path)
    tool = document.get("tool")
    maturin = tool.get("maturin") if isinstance(tool, Mapping) else None
    includes = maturin.get("include") if isinstance(maturin, Mapping) else None
    if includes is None:
        return ()
    if not isinstance(includes, list) or not all(isinstance(pattern, str) for pattern in includes):
        raise DistributionConfigurationError("tool.maturin.include must be a list of path patterns")

    root = project_root.resolve()
    included: set[Path] = set()
    for pattern in includes:
        candidate_pattern = Path(pattern)
        if candidate_pattern.is_absolute() or ".." in candidate_pattern.parts:
            raise DistributionConfigurationError(
                f"Maturin include pattern must stay within the project root: {pattern}"
            )
        matches = tuple(path for path in root.glob(pattern) if path.is_file())
        if not matches:
            raise DistributionConfigurationError(
                f"Maturin include pattern did not match a file: {pattern}"
            )
        included.update(_relative_to_root(path, root) for path in matches)
    return tuple(sorted(included, key=lambda path: path.as_posix()))


def sdist_file_paths(sdist_path: Path) -> tuple[set[PurePosixPath], PurePosixPath]:
    """Return regular file paths and the detected top-level directory of an sdist."""

    with tarfile.open(sdist_path, "r:gz") as archive:
        files = {
            _normalise_archive_path(member.name)
            for member in archive.getmembers()
            if member.isfile()
        }

    pyproject_parents = {path.parent for path in files if path.name == PYPROJECT.name}
    if len(pyproject_parents) != 1:
        raise DistributionConfigurationError(
            "Could not identify one source-distribution root containing pyproject.toml"
        )
    return files, pyproject_parents.pop()


def stub_surface(stub_contents: str) -> tuple[dict[str, ast.FunctionDef], set[str]]:
    """Return public module functions and classes declared by a native stub."""

    tree = ast.parse(stub_contents)
    functions: dict[str, ast.FunctionDef] = {}
    classes: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, ast.FunctionDef) and not statement.name.startswith("_"):
            functions[statement.name] = statement
        elif isinstance(statement, ast.ClassDef) and not statement.name.startswith("_"):
            classes.add(statement.name)
    return functions, classes


def stub_signature(function: ast.FunctionDef) -> tuple[tuple[str, str, bool, object], ...]:
    """Return parameter names, kinds, and literal defaults declared in a stub."""

    positional = [*function.args.posonlyargs, *function.args.args]
    defaults: list[ast.expr | object] = [_NO_DEFAULT] * (
        len(positional) - len(function.args.defaults)
    ) + list(function.args.defaults)
    parameters: list[tuple[str, str, bool, object]] = []
    for index, argument in enumerate(positional):
        default = defaults[index]
        has_default = isinstance(default, ast.expr)
        parameters.append(
            (
                argument.arg,
                "POSITIONAL_ONLY"
                if index < len(function.args.posonlyargs)
                else "POSITIONAL_OR_KEYWORD",
                has_default,
                _literal_default(default) if has_default else None,
            )
        )
    if function.args.vararg is not None:
        parameters.append((function.args.vararg.arg, "VAR_POSITIONAL", False, None))
    for argument, default in zip(function.args.kwonlyargs, function.args.kw_defaults, strict=True):
        parameters.append(
            (
                argument.arg,
                "KEYWORD_ONLY",
                default is not None,
                _literal_default(default) if default is not None else None,
            )
        )
    if function.args.kwarg is not None:
        parameters.append((function.args.kwarg.arg, "VAR_KEYWORD", False, None))
    return tuple(parameters)


def runtime_signature(
    parameters: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, str, bool, object], ...]:
    """Normalise JSON-safe ``inspect.Signature`` data from an installed extension."""

    return tuple(
        (
            str(parameter["name"]),
            str(parameter["kind"]),
            bool(parameter["has_default"]),
            parameter["default"] if parameter["has_default"] else None,
        )
        for parameter in parameters
    )


def extension_surface_drift(
    stub_contents: str, runtime_surface: Mapping[str, object]
) -> tuple[str, ...]:
    """Return concrete native-stub symbol/signature differences.

    Module-level functions form the native callable ABI and must agree in both
    directions.  Class names are also checked in both directions; class method
    annotations remain type-checker interfaces and are validated by the isolated
    consumer check.
    """

    stub_functions, stub_classes = stub_surface(stub_contents)
    runtime_functions = runtime_surface.get("functions")
    runtime_classes = runtime_surface.get("classes")
    if not isinstance(runtime_functions, Mapping) or not isinstance(runtime_classes, list):
        raise DistributionConfigurationError(
            "Installed extension returned malformed surface metadata"
        )

    drift: list[str] = []
    runtime_function_names = set(runtime_functions)
    for name in sorted(set(stub_functions) - runtime_function_names):
        drift.append(f"stub declares missing extension function: {name}")
    for name in sorted(runtime_function_names - set(stub_functions)):
        drift.append(f"extension function is missing from stub: {name}")
    for name in sorted(set(stub_functions) & runtime_function_names):
        parameters = runtime_functions[name]
        if not isinstance(parameters, list):
            drift.append(f"extension returned malformed signature for {name}")
            continue
        if stub_signature(stub_functions[name]) != runtime_signature(parameters):
            drift.append(
                f"signature mismatch for {name}: stub {stub_signature(stub_functions[name])!r} "
                f"!= extension {runtime_signature(parameters)!r}"
            )

    runtime_class_names = {str(name) for name in runtime_classes}
    for name in sorted(stub_classes - runtime_class_names):
        drift.append(f"stub declares missing extension class: {name}")
    for name in sorted(runtime_class_names - stub_classes):
        drift.append(f"extension class is missing from stub: {name}")
    return tuple(drift)


def _verify_extension_surface(wheel_path: Path, module_name: str) -> None:
    with zipfile.ZipFile(wheel_path) as archive:
        stub_path = f"{RUST_PACKAGE_ROOT.as_posix()}/{module_name.rsplit('.', maxsplit=1)[-1]}.pyi"
        try:
            stub_contents = archive.read(stub_path).decode("utf-8")
        except KeyError as error:
            raise DistributionConfigurationError(
                f"Wheel is missing native stub: {stub_path}"
            ) from error

    surface = _installed_extension_surface(wheel_path, module_name)
    drift = extension_surface_drift(stub_contents, surface)
    if drift:
        raise DistributionConfigurationError(
            f"Native stub drift in {wheel_path.name} for {module_name}:\n"
            + "\n".join(f"  {item}" for item in drift)
        )


def _installed_extension_surface(wheel_path: Path, module_name: str) -> Mapping[str, object]:
    command = [
        "uv",
        "run",
        "--isolated",
        "--with",
        str(wheel_path),
        "python",
        "-c",
        _NATIVE_SURFACE_SCRIPT,
        module_name,
    ]
    completed = subprocess.run(
        command,
        check=True,
        cwd=_isolated_working_directory(),
        env=_isolated_environment(),
        capture_output=True,
        text=True,
    )
    try:
        surface = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise DistributionConfigurationError(
            f"Could not read installed extension surface for {module_name}: {completed.stdout!r}"
        ) from error
    if not isinstance(surface, Mapping):
        raise DistributionConfigurationError(
            f"Installed extension surface for {module_name} is not a mapping"
        )
    return surface


def _run_isolated_consumer_checks(wheel_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="gummysnake-wheel-contract-") as temporary:
        consumer = Path(temporary) / "consumer.py"
        consumer.write_text(_WHEEL_CONSUMER_SCRIPT, encoding="utf-8")
        base_command = ["uv", "run", "--isolated", "--with", str(wheel_path)]
        subprocess.run(
            [*base_command, "--with", "mypy", "mypy", "--strict", str(consumer)],
            check=True,
            cwd=Path(temporary),
            env=_isolated_environment(),
        )
        subprocess.run(
            [*base_command, "python", str(consumer)],
            check=True,
            cwd=Path(temporary),
            env=_isolated_environment(),
        )


def _isolated_working_directory() -> Path:
    """Use a temporary non-checkout directory so imports cannot resolve ``src/``."""

    return Path(tempfile.gettempdir())


def _isolated_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def _literal_default(node: ast.expr) -> object:
    try:
        return ast.literal_eval(node)
    except ValueError as error:
        raise DistributionConfigurationError(
            f"Native stub defaults must be literals, got {ast.unparse(node)}"
        ) from error


def _dependency_tables(document: Mapping[str, object]) -> Iterable[Mapping[str, object]]:
    for section in DEPENDENCY_SECTIONS:
        dependencies = document.get(section)
        if isinstance(dependencies, Mapping):
            yield dependencies

    targets = document.get("target")
    if not isinstance(targets, Mapping):
        return
    for target in targets.values():
        if not isinstance(target, Mapping):
            continue
        for section in DEPENDENCY_SECTIONS:
            dependencies = target.get(section)
            if isinstance(dependencies, Mapping):
                yield dependencies


def _crate_source_paths(crate_directory: Path, project_root: Path) -> tuple[Path, ...]:
    source_directory = crate_directory / "src"
    source_paths = (
        (
            _relative_to_root(path, project_root)
            for path in source_directory.rglob("*")
            if path.is_file()
        )
        if source_directory.is_dir()
        else ()
    )
    build_script = crate_directory / "build.rs"
    if build_script.is_file():
        source_paths = (*source_paths, _relative_to_root(build_script, project_root))
    return tuple(sorted(set(source_paths), key=lambda path: path.as_posix()))


def _read_toml(path: Path) -> Mapping[str, object]:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise DistributionConfigurationError(f"Could not read TOML manifest: {path}") from error
    if not isinstance(document, Mapping):
        raise DistributionConfigurationError(f"TOML manifest must contain a table: {path}")
    return document


def _relative_to_root(path: Path, project_root: Path) -> Path:
    try:
        return path.resolve().relative_to(project_root.resolve())
    except ValueError as error:
        raise DistributionConfigurationError(
            f"Required path is outside the project root: {path}"
        ) from error


def _normalise_archive_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise DistributionConfigurationError(f"Unsafe path in source distribution: {name}")
    return PurePosixPath(*(part for part in path.parts if part != "."))


def _archive_member_path(archive_root: PurePosixPath, path: Path) -> PurePosixPath:
    relative = PurePosixPath(path.as_posix())
    return relative if archive_root == PurePosixPath(".") else archive_root / relative


def _print_missing(label: str, missing: Sequence[Path]) -> None:
    print(f"{label} is missing required paths:", file=sys.stderr)
    for path in missing:
        print(f"  {path.as_posix()}", file=sys.stderr)


_NATIVE_SURFACE_SCRIPT = textwrap.dedent(
    """
    import importlib
    import inspect
    import json
    import sys

    module = importlib.import_module(sys.argv[1])
    native_suffixes = (".so", ".pyd", ".dylib")
    if not module.__file__ or not module.__file__.endswith(native_suffixes):
        raise SystemExit(
            f"{sys.argv[1]} did not import from a native extension: {module.__file__!r}"
        )
    functions = {}
    classes = []
    for name in dir(module):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if inspect.isbuiltin(value):
            functions[name] = [
                {
                    "name": parameter.name,
                    "kind": parameter.kind.name,
                    "has_default": parameter.default is not inspect.Parameter.empty,
                    "default": None
                    if parameter.default is inspect.Parameter.empty
                    else parameter.default,
                }
                for parameter in inspect.signature(value).parameters.values()
            ]
        elif inspect.isclass(value) and value.__module__ == "builtins":
            classes.append(name)
    print(json.dumps({"functions": functions, "classes": sorted(classes)}, sort_keys=True))
    """
).strip()


_WHEEL_CONSUMER_SCRIPT = (
    textwrap.dedent(
        """
    from __future__ import annotations

    import importlib.metadata
    from pathlib import Path

    import gummysnake
    from gummysnake import synth as sy
    from gummysnake.rust import _canvas
    from gummysnake.rust.canvas import (
        EXPECTED_CANVAS_ABI_VERSION,
        canvas_abi_version,
        canvas_health_check,
        require_canvas_runtime,
    )
    from gummysnake.rust.ecs import (
        EXPECTED_ECS_ABI_VERSION,
        create_ecs_world,
        ecs_abi_version,
        ecs_health_check,
        require_ecs_runtime,
    )


    @sy.track
    def wheel_contract_track() -> None:
        sy.sample("bd_haus", amp=0.1)
        sy.sleep(0.01)


    def main() -> None:
        installed_package = importlib.metadata.distribution("gummy-snake").locate_file(
            "gummysnake"
        )
        package_file = Path(gummysnake.__file__).resolve()
        if Path(str(installed_package)).resolve() not in package_file.parents:
            raise SystemExit(
                f"consumer imported Gummy Snake outside its installed wheel: {package_file}"
            )
        if not _canvas.__file__ or not _canvas.__file__.endswith(
            (".so", ".pyd", ".dylib")
        ):
            raise SystemExit("wheel did not import the mandatory native canvas extension")
        if (
            canvas_health_check() != "rust-canvas"
            or canvas_abi_version() != EXPECTED_CANVAS_ABI_VERSION
        ):
            raise SystemExit(
                "installed wheel has an unhealthy or ABI-incompatible canvas extension"
            )
        if (
            not ecs_health_check().startswith("gummy-ecs")
            or ecs_abi_version() != EXPECTED_ECS_ABI_VERSION
        ):
            raise SystemExit("installed wheel has an unhealthy or ABI-incompatible ECS bridge")
        require_canvas_runtime()
        runtime = require_ecs_runtime()
        world = create_ecs_world()
        if not hasattr(runtime, "EcsSpatialIndexRegistry") or world.alive_count() != 0:
            raise SystemExit("installed wheel failed the Rust-owned empty ECS world contract")

        canvas = _canvas.Canvas(8, 8, 1.0, "headless", "p2d")
        try:
            canvas.begin_frame()
            canvas.background((12, 34, 56, 255))
            canvas.end_frame()
            pixels = canvas.load_pixel_bytes()
            if len(pixels) != 8 * 8 * 4 or pixels[:4] != bytes((12, 34, 56, 255)):
                raise SystemExit(
                    "installed wheel did not render the expected headless canvas frame"
                )
        finally:
            canvas.close()

        if "dsaw" not in sy.builtin_synth_names() or "reverb" not in sy.builtin_fx_names():
            raise SystemExit("installed wheel cannot find packaged compiled synth or FX assets")
        payload = wheel_contract_track().render(duration=0.02, sample_rate=8_000)
        if not payload.startswith(b"RIFF") or len(payload) <= 44:
            raise SystemExit("installed wheel did not render a non-empty Rust synth WAV")


    if __name__ == "__main__":
        main()
    """
    ).strip()
    + "\n"
)


if __name__ == "__main__":
    raise SystemExit(main())
