#!/usr/bin/env python3
"""Audit source-tree organization conventions for Gummy Snake.

This is intentionally lightweight: it catches naming/layout regressions that are
confusing for navigation but do not require running the full test suite.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "target",
}
IGNORED_RELATIVE_DIRS = (Path("examples/output"),)
EXAMPLE_CATALOG_PATH = Path("examples/example_catalog.toml")
EXAMPLE_CLASSIFICATIONS = frozenset(
    {"entry_point", "support_module", "compatibility_entry_point", "generated"}
)
EXAMPLE_ENTRY_CLASSIFICATIONS = frozenset({"entry_point", "compatibility_entry_point"})
EXAMPLE_SMOKE_TIERS = frozenset({"none", "fast", "extended", "release"})
EXAMPLE_ALLOWED_EXTRAS = frozenset({"media", "numpy"})
EXAMPLE_REQUIRED_FAST_IDS = frozenset(
    {
        "basic_shapes",
        "images_and_sprites",
        "typography_accessibility",
        "lifecycle_controls",
        "firefly_constellation",
        "webgl_scene",
        "wob_rhythm",
    }
)
EXPECTED_GENERATED_IGNORE_ENTRIES = frozenset(
    {
        "examples/output/",
        "__pycache__/",
        ".mypy_cache/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".cache",
        "build/",
        "dist/",
        "target/",
    }
)
CACHE_DIRECTORY_NAMES = frozenset(
    {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache", ".venv"}
)
ROOT_GENERATED_DIRECTORY_NAMES = frozenset({"build", "dist", "target", "htmlcov", "cover"})
COMPILED_ARTIFACT_SUFFIXES = frozenset({".pyc", ".pyo", ".so", ".dylib", ".dll", ".pyd"})
WORKFLOW_RUN_RE = re.compile(r"^(?P<indent>\s*)(?:-\s*)?run:\s*(?P<command>.*)$")
PYTHON_LAYOUT_ROOTS = (Path("src"), Path("tests"), Path("examples"))
TEXT_ROOTS = (
    Path("src"),
    Path("tests"),
    Path("examples"),
    Path("docs"),
    Path("scripts"),
    Path("README.md"),
    Path("AGENTS.md"),
)
TEXT_SUFFIXES = {".py", ".rs", ".md", ".toml", ".txt", ".yaml", ".yml", ".json"}
SELF_REFERENTIAL_AUDIT_FILES = {
    Path("scripts/structure_audit.py"),
    Path("tests/unit/tooling/test_structure_audit.py"),
}
REPOSITORY_PATH_PREFIXES = (
    "src/",
    "crates/",
    "tests/",
    "examples/",
    "docs/",
    "scripts/",
)
PATH_SKIP_MARKERS = ("...", "<", ">")
PATH_WILDCARD_CHARACTERS = frozenset("*?[]{}")
SUPPORT_CLUSTER_DIRECTORIES = (Path("tests/helpers"),)
INTENTIONAL_SUPPORT_PREFIX_CLUSTERS: dict[Path, frozenset[str]] = {}
MARKDOWN_INLINE_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\((?P<destination><[^>\n]+>|[^)\n]+)\)")
INLINE_CODE_SPAN_RE = re.compile(r"(?<!`)`(?P<content>[^`\n]+)`(?!`)")
STALE_TEXT_PATTERNS = {
    "renderer3d_support": "use the `gummysnake.drawing.renderer3d` package instead",
    "backend/_canvas": "use `backend/canvas_runtime` instead",
    "backend._canvas": "use `backend.canvas_runtime` instead",
    "gummysnake.backend._canvas": "use `gummysnake.backend.canvas_runtime` instead",
    "gummysnake._context": "use `gummysnake.context_mixins` instead",
    "src/gummysnake/_context": "use `src/gummysnake/context_mixins` instead",
    "core/_state": "use `core/state_facades` instead",
    "core._state": "use `core.state_facades` instead",
    "sketch/_facade": "use `sketch/facade_mixins` instead",
    "sketch._facade": "use `sketch.facade_mixins` instead",
    "canvas_runtime/backend": "use `canvas_runtime/host` instead",
    "canvas_runtime.backend": "use `canvas_runtime.host` instead",
    "gummysnake.assets.image.model": "use `gummysnake.assets.image.core` instead",
    "assets/image/model.py": "use `assets/image/core.py` instead",
    "rust_canvas_context_helpers": "use `tests.helpers.canvas_runtime.context` instead",
    "rust_canvas_asset_fakes": "use `tests.helpers.canvas_runtime.assets` instead",
    "rust_canvas_image_fakes": "use `tests.helpers.canvas_runtime.image_kernels` instead",
    "rust_canvas_state_fakes": "use `tests.helpers.canvas_runtime.state` instead",
    "webgl_helpers": "use `tests.helpers.webgl` instead",
    "gummysnake.events.input_state": "use `gummysnake.core.input_events` instead",
    "gummysnake.events.input_events": "use `gummysnake.core.input_events` instead",
}
DOCUMENTED_RUST_HUBS = {
    Path("crates/gummy_canvas/src/bindings.rs"),
    Path("crates/gummy_canvas/src/bindings/ecs.rs"),
    Path("crates/gummy_canvas/src/bindings/models.rs"),
    Path("crates/gummy_canvas/src/canvas/gpu.rs"),
    Path("crates/gummy_canvas/src/canvas/gpu/shapes.rs"),
    Path("crates/gummy_canvas/src/canvas/lifecycle.rs"),
    Path("crates/gummy_canvas/src/canvas/pixels.rs"),
    Path("crates/gummy_canvas/src/canvas/primitives.rs"),
    Path("crates/gummy_canvas/src/canvas/primitives/batches.rs"),
    Path("crates/gummy_canvas/src/gpu/pipeline.rs"),
    Path("crates/gummy_canvas/src/gpu/render.rs"),
    Path("crates/gummy_canvas/src/gpu/setup.rs"),
    Path("crates/gummy_canvas/src/gpu/shaders.rs"),
    Path("crates/gummy_canvas/src/gpu/shaders/primitive.rs"),
    Path("crates/gummy_canvas/src/gpu/types.rs"),
    Path("crates/gummy_canvas/src/runtime/desktop.rs"),
    Path("crates/gummy_canvas/src/sketch_state.rs"),
    Path("crates/gummy_canvas/src/sound.rs"),
    Path("crates/gummy_canvas/src/tests.rs"),
    Path("crates/gummy_ecs/src/execution.rs"),
    Path("crates/gummy_ecs/src/execution/interpreter/actions.rs"),
    Path("crates/gummy_ecs/src/execution/optimized/f64_program.rs"),
    Path("crates/gummy_ecs/src/execution/row_local/compact_fill.rs"),
    Path("crates/gummy_ecs/src/execution/tests.rs"),
    Path("crates/gummy_ecs/src/plan.rs"),
    Path("crates/gummy_ecs/src/spatial.rs"),
    Path("crates/gummy_ecs/src/spatial/hash_grid.rs"),
    Path("crates/gummy_ecs/src/spatial/tree_spatial.rs"),
    Path("crates/gummy_ecs/src/world.rs"),
}


@dataclass(frozen=True, slots=True)
class StructureViolation:
    code: str
    path: Path
    message: str


def _has_ignored_part(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def _is_ignored_relative_path(path: Path) -> bool:
    return _has_ignored_part(path) or any(
        path == ignored or ignored in path.parents for ignored in IGNORED_RELATIVE_DIRS
    )


def _display_path(repo_root: Path, path: Path) -> Path:
    try:
        return path.relative_to(repo_root)
    except ValueError:
        return path


def _iter_existing_dirs(repo_root: Path, roots: tuple[Path, ...]) -> list[Path]:
    directories: list[Path] = []
    for relative_root in roots:
        root = repo_root / relative_root
        if not root.exists():
            continue
        if root.is_dir() and not _is_ignored_relative_path(relative_root):
            directories.append(root)
            directories.extend(
                path
                for path in root.rglob("*")
                if path.is_dir() and not _is_ignored_relative_path(_display_path(repo_root, path))
            )
    return directories


def _workspace_member_source_roots(repo_root: Path) -> tuple[Path, ...]:
    """Return source roots for workspace members declared by the root manifest."""
    manifest_path = repo_root / "Cargo.toml"
    if not manifest_path.is_file():
        return ()

    try:
        manifest = tomllib.loads(manifest_path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return ()

    workspace = manifest.get("workspace")
    if not isinstance(workspace, dict):
        return ()
    members = workspace.get("members")
    if not isinstance(members, list):
        return ()

    source_roots: set[Path] = set()
    for member in members:
        if not isinstance(member, str):
            continue
        for member_path in repo_root.glob(member):
            if not member_path.is_dir() or not (member_path / "Cargo.toml").is_file():
                continue
            try:
                relative_member = member_path.relative_to(repo_root)
            except ValueError:
                continue
            if _is_ignored_relative_path(relative_member):
                continue
            source_roots.add(relative_member / "src")
    return tuple(sorted(source_roots))


def _iter_text_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    roots = (*TEXT_ROOTS, *_workspace_member_source_roots(repo_root))
    for relative_root in dict.fromkeys(roots):
        root = repo_root / relative_root
        if not root.exists() or _is_ignored_relative_path(relative_root):
            continue
        if root.is_file():
            if root.suffix in TEXT_SUFFIXES:
                files.append(root)
            continue
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix in TEXT_SUFFIXES
            and not _is_ignored_relative_path(_display_path(repo_root, path))
        )
    return files


def _iter_markdown_files(repo_root: Path) -> list[Path]:
    return sorted(
        path
        for path in repo_root.rglob("*.md")
        if path.is_file() and not _is_ignored_relative_path(_display_path(repo_root, path))
    )


def _iter_non_fenced_lines(text: str) -> list[str]:
    lines: list[str] = []
    fence_marker: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if fence_marker is None:
                fence_marker = marker
            elif marker == fence_marker:
                fence_marker = None
            continue
        if fence_marker is None:
            lines.append(line)
    return lines


def _should_skip_path(path: str) -> bool:
    return (
        not path
        or any(marker in path for marker in PATH_SKIP_MARKERS)
        or any(character in path for character in PATH_WILDCARD_CHARACTERS)
    )


def _is_within_repo(repo_root: Path, path: Path) -> bool:
    try:
        path.relative_to(repo_root)
    except ValueError:
        return False
    return True


def _audit_python_sibling_packages(repo_root: Path) -> list[StructureViolation]:
    violations: list[StructureViolation] = []
    for directory in _iter_existing_dirs(repo_root, PYTHON_LAYOUT_ROOTS):
        module_stems = {
            child.stem
            for child in directory.iterdir()
            if child.is_file() and child.suffix == ".py" and child.name != "__init__.py"
        }
        package_names = {child.name for child in directory.iterdir() if child.is_dir()}
        for stem in sorted(module_stems):
            private_package = f"_{stem}"
            if private_package in package_names:
                violations.append(
                    StructureViolation(
                        "python_private_sibling_package",
                        _display_path(repo_root, directory / private_package),
                        (
                            f"avoid `{stem}.py` next to `{private_package}/`; "
                            "use a descriptive package name"
                        ),
                    )
                )
            if stem in package_names:
                violations.append(
                    StructureViolation(
                        "python_same_stem_module_package",
                        _display_path(repo_root, directory / stem),
                        (
                            f"avoid ambiguous `{stem}.py` next to `{stem}/`; "
                            "choose either module or package"
                        ),
                    )
                )
    return violations


def _audit_python_support_prefix_clusters(repo_root: Path) -> list[StructureViolation]:
    violations: list[StructureViolation] = []
    for relative_directory in SUPPORT_CLUSTER_DIRECTORIES:
        directory = repo_root / relative_directory
        if not directory.is_dir():
            continue
        prefixes: dict[str, list[Path]] = {}
        for child in directory.iterdir():
            if child.suffix != ".py" or not child.is_file() or "_" not in child.stem:
                continue
            prefix, _ = child.stem.rsplit("_", 1)
            if prefix:
                prefixes.setdefault(prefix, []).append(child)
        allowed_prefixes = INTENTIONAL_SUPPORT_PREFIX_CLUSTERS.get(relative_directory, frozenset())
        for prefix, paths in sorted(prefixes.items()):
            if len(paths) < 4 or prefix in allowed_prefixes:
                continue
            names = ", ".join(path.name for path in sorted(paths))
            violations.append(
                StructureViolation(
                    "python_support_prefix_cluster",
                    relative_directory,
                    (
                        f"Python support files share the `{prefix}_` prefix: {names}; "
                        "group related support modules into a package"
                    ),
                )
            )
    return violations


def _audit_source_testing_package(repo_root: Path) -> list[StructureViolation]:
    testing_path = repo_root / "src/gummysnake/testing"
    if testing_path.exists():
        return [
            StructureViolation(
                "source_testing_package",
                Path("src/gummysnake/testing"),
                (
                    "test fixtures/helpers belong under `tests/fixtures` or `tests/helpers`, "
                    "not package source"
                ),
            )
        ]
    return []


def _audit_obsolete_source_packages(repo_root: Path) -> list[StructureViolation]:
    violations: list[StructureViolation] = []
    obsolete_paths = {
        Path("src/gummysnake/pixels.py"): (
            "obsolete_pixels_module",
            "pixel buffer helpers belong in `src/gummysnake/core/pixels.py`",
        ),
        Path("src/gummysnake/pixels"): (
            "obsolete_pixels_module",
            "pixel buffer helpers belong in `src/gummysnake/core/pixels.py`",
        ),
        Path("src/gummysnake/events.py"): (
            "obsolete_events_module",
            "input event dataclasses belong in `src/gummysnake/core/input_events.py`",
        ),
        Path("src/gummysnake/events"): (
            "obsolete_events_module",
            "input event dataclasses belong in `src/gummysnake/core/input_events.py`",
        ),
    }
    for relative_path, (code, message) in obsolete_paths.items():
        if (repo_root / relative_path).exists():
            violations.append(StructureViolation(code, relative_path, message))
    return violations


def _audit_stale_text_references(repo_root: Path) -> list[StructureViolation]:
    violations: list[StructureViolation] = []
    for path in _iter_text_files(repo_root):
        relative = _display_path(repo_root, path)
        if relative in SELF_REFERENTIAL_AUDIT_FILES:
            continue
        text = path.read_text(errors="ignore")
        for pattern, replacement in STALE_TEXT_PATTERNS.items():
            if pattern in text:
                violations.append(
                    StructureViolation(
                        "stale_layout_reference",
                        relative,
                        f"found `{pattern}`; {replacement}",
                    )
                )
    return violations


def _audit_local_markdown_links(repo_root: Path) -> list[StructureViolation]:
    violations: list[StructureViolation] = []
    for path in _iter_markdown_files(repo_root):
        relative = _display_path(repo_root, path)
        if relative in SELF_REFERENTIAL_AUDIT_FILES:
            continue
        destinations: set[str] = set()
        for line in _iter_non_fenced_lines(path.read_text(errors="ignore")):
            for match in MARKDOWN_INLINE_LINK_RE.finditer(line):
                destination = match.group("destination").strip().split(maxsplit=1)[0]
                destination = unquote(destination).split("#", 1)[0].split("?", 1)[0]
                if (
                    _should_skip_path(destination)
                    or destination.startswith(("#", "/", "\\"))
                    or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", destination)
                ):
                    continue
                destinations.add(destination)
        for destination in sorted(destinations):
            target = (path.parent / destination).resolve()
            if _is_within_repo(repo_root, target) and target.exists():
                continue
            violations.append(
                StructureViolation(
                    "missing_markdown_link",
                    relative,
                    f"local Markdown link target `{destination}` does not exist",
                )
            )
    return violations


def _audit_backticked_repository_paths(repo_root: Path) -> list[StructureViolation]:
    violations: list[StructureViolation] = []
    for path in _iter_text_files(repo_root):
        relative = _display_path(repo_root, path)
        if relative in SELF_REFERENTIAL_AUDIT_FILES:
            continue
        candidates: set[str] = set()
        for line in _iter_non_fenced_lines(path.read_text(errors="ignore")):
            for match in INLINE_CODE_SPAN_RE.finditer(line):
                content = match.group("content").strip()
                if not content:
                    continue
                candidate = content.split(maxsplit=1)[0]
                if candidate.startswith(REPOSITORY_PATH_PREFIXES) and not _should_skip_path(
                    candidate
                ):
                    candidates.add(candidate)
        for candidate in sorted(candidates):
            target = (repo_root / candidate).resolve()
            if _is_within_repo(repo_root, target) and target.exists():
                continue
            violations.append(
                StructureViolation(
                    "stale_repository_path",
                    relative,
                    f"backticked repository path `{candidate}` does not exist",
                )
            )
    return violations


def _gitignore_entries(repo_root: Path) -> set[str]:
    gitignore = repo_root / ".gitignore"
    if not gitignore.is_file():
        return set()
    return {
        line.strip()
        for line in gitignore.read_text(errors="ignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _audit_example_catalog(repo_root: Path) -> list[StructureViolation]:
    examples_root = repo_root / "examples"
    catalog_path = repo_root / EXAMPLE_CATALOG_PATH
    if not examples_root.is_dir():
        return []
    if not catalog_path.is_file():
        return [
            StructureViolation(
                "missing_example_catalog",
                EXAMPLE_CATALOG_PATH,
                "add a machine-readable catalog for every examples Python file",
            )
        ]

    try:
        catalog = tomllib.loads(catalog_path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        return [
            StructureViolation(
                "invalid_example_catalog",
                EXAMPLE_CATALOG_PATH,
                f"catalog must be valid TOML: {error}",
            )
        ]

    violations: list[StructureViolation] = []
    if catalog.get("catalog") != {"version": 1}:
        violations.append(
            StructureViolation(
                "invalid_example_catalog_schema",
                EXAMPLE_CATALOG_PATH,
                "catalog must declare `[catalog]` with `version = 1`",
            )
        )

    entries = catalog.get("files")
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        return [
            *violations,
            StructureViolation(
                "invalid_example_catalog_schema",
                EXAMPLE_CATALOG_PATH,
                "catalog must declare one or more `[[files]]` tables",
            ),
        ]

    discovered_paths = {
        _display_path(repo_root, path)
        for path in examples_root.rglob("*.py")
        if path.is_file() and not _is_ignored_relative_path(_display_path(repo_root, path))
    }
    catalog_paths: set[Path] = set()
    entries_by_id: dict[str, Mapping[str, object]] = {}
    historical_entries: list[Mapping[str, object]] = []
    smoke_ids: dict[str, set[str]] = {tier: set() for tier in EXAMPLE_SMOKE_TIERS - {"none"}}

    for entry in entries:
        path_value = entry.get("path")
        classification = entry.get("classification")
        topic = entry.get("topic")
        if not isinstance(path_value, str):
            violations.append(
                StructureViolation(
                    "invalid_example_catalog_entry",
                    EXAMPLE_CATALOG_PATH,
                    "each `[[files]]` entry needs a string `path`",
                )
            )
            continue
        path = Path(path_value)
        catalog_paths.add(path)
        if not path_value.startswith("examples/") or path.suffix != ".py":
            violations.append(
                StructureViolation(
                    "invalid_example_catalog_path",
                    path,
                    "catalog paths must be Python files under `examples/`",
                )
            )
            continue
        if not (repo_root / path).is_file():
            violations.append(
                StructureViolation(
                    "stale_example_catalog_path",
                    path,
                    "catalog path does not exist",
                )
            )
        if classification not in EXAMPLE_CLASSIFICATIONS:
            violations.append(
                StructureViolation(
                    "invalid_example_catalog_classification",
                    path,
                    f"classification must be one of {sorted(EXAMPLE_CLASSIFICATIONS)}",
                )
            )
        if not isinstance(topic, str) or not topic.strip():
            violations.append(
                StructureViolation(
                    "invalid_example_catalog_topic",
                    path,
                    "each catalog entry needs a non-empty topic",
                )
            )
        if classification not in EXAMPLE_ENTRY_CLASSIFICATIONS:
            continue

        required_keys = {
            "id",
            "extras",
            "assets",
            "capabilities",
            "flags",
            "output",
            "output_behavior",
            "headless",
            "smoke_tier",
            "smoke_args",
            "performance_only",
            "compatibility",
        }
        missing_keys = sorted(required_keys - entry.keys())
        if missing_keys:
            violations.append(
                StructureViolation(
                    "incomplete_example_catalog_entry",
                    path,
                    f"entry point is missing: {', '.join(missing_keys)}",
                )
            )
            continue

        entry_id = entry["id"]
        if not isinstance(entry_id, str) or not entry_id:
            violations.append(
                StructureViolation(
                    "invalid_example_catalog_id",
                    path,
                    "entry point `id` must be a non-empty string",
                )
            )
        elif entry_id in entries_by_id:
            violations.append(
                StructureViolation(
                    "duplicate_example_catalog_id",
                    path,
                    f"duplicate entry point id `{entry_id}`",
                )
            )
        else:
            entries_by_id[entry_id] = entry

        for field in ("extras", "assets", "capabilities", "flags", "smoke_args"):
            value = entry[field]
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                violations.append(
                    StructureViolation(
                        "invalid_example_catalog_field",
                        path,
                        f"`{field}` must be a list of strings",
                    )
                )
        extras = entry["extras"]
        if isinstance(extras, list):
            for extra in extras:
                if isinstance(extra, str) and extra not in EXAMPLE_ALLOWED_EXTRAS:
                    violations.append(
                        StructureViolation(
                            "unknown_example_extra",
                            path,
                            f"`{extra}` is not a declared optional dependency extra",
                        )
                    )
        assets = entry["assets"]
        if isinstance(assets, list):
            for asset in assets:
                if not isinstance(asset, str) or not (repo_root / asset).exists():
                    violations.append(
                        StructureViolation(
                            "missing_example_asset",
                            path,
                            f"declared asset `{asset}` does not exist",
                        )
                    )
        output = entry["output"]
        if not isinstance(output, str) or not output.startswith("examples/output/"):
            violations.append(
                StructureViolation(
                    "invalid_example_output_policy",
                    path,
                    "entry output must be a path below `examples/output/`",
                )
            )
        if not isinstance(entry["output_behavior"], str) or not entry["output_behavior"].strip():
            violations.append(
                StructureViolation(
                    "invalid_example_output_behavior",
                    path,
                    "entry point needs a non-empty output_behavior",
                )
            )
        if not isinstance(entry["headless"], bool) or not isinstance(
            entry["performance_only"], bool
        ):
            violations.append(
                StructureViolation(
                    "invalid_example_catalog_field",
                    path,
                    "`headless` and `performance_only` must be booleans",
                )
            )
        smoke_tier = entry["smoke_tier"]
        smoke_args = entry["smoke_args"]
        if smoke_tier not in EXAMPLE_SMOKE_TIERS:
            violations.append(
                StructureViolation(
                    "invalid_example_smoke_tier",
                    path,
                    f"smoke_tier must be one of {sorted(EXAMPLE_SMOKE_TIERS)}",
                )
            )
        elif smoke_tier != "none":
            if (
                not entry["headless"]
                or not isinstance(smoke_args, list)
                or "--no-save" not in smoke_args
            ):
                violations.append(
                    StructureViolation(
                        "unsafe_example_smoke_command",
                        path,
                        "bounded smoke entries must be headless and include --no-save",
                    )
                )
            capabilities = entry["capabilities"]
            if (
                isinstance(capabilities, list)
                and "synth" in capabilities
                and (not isinstance(smoke_args, list) or "--no-play" not in smoke_args)
            ):
                violations.append(
                    StructureViolation(
                        "unsafe_example_smoke_command",
                        path,
                        "synth smoke entries must include --no-play",
                    )
                )
            if isinstance(entry_id, str):
                smoke_ids[smoke_tier].add(entry_id)

        source = (
            (repo_root / path).read_text(errors="ignore") if (repo_root / path).is_file() else ""
        )
        flag_source = entry.get("flag_source")
        if isinstance(flag_source, str):
            flag_source_path = repo_root / flag_source
            if not flag_source_path.is_file():
                violations.append(
                    StructureViolation(
                        "stale_example_catalog_flag_source",
                        path,
                        f"flag_source `{flag_source}` does not exist",
                    )
                )
            else:
                source = flag_source_path.read_text(errors="ignore")
        elif flag_source is not None:
            violations.append(
                StructureViolation(
                    "invalid_example_catalog_flag_source",
                    path,
                    "flag_source must be a repository-relative string when provided",
                )
            )
        flags = entry["flags"]
        supports_common_flags = (
            "example_parser" in source
            or (" import run" in source and "run(__doc__)" in source)
            or "_configuration.ARGS" in source
        )
        for flag in flags if isinstance(flags, list) else []:
            if (
                not supports_common_flags
                and flag not in source
                and classification != "compatibility_entry_point"
            ):
                violations.append(
                    StructureViolation(
                        "stale_example_catalog_flag",
                        path,
                        f"flag `{flag}` is not defined by this entry point",
                    )
                )

        compatibility = entry["compatibility"]
        if compatibility == "historical":
            historical_entries.append(entry)
        elif compatibility != "canonical":
            violations.append(
                StructureViolation(
                    "invalid_example_compatibility",
                    path,
                    "entry point compatibility must be `canonical` or `historical`",
                )
            )

    for path in sorted(discovered_paths - catalog_paths):
        violations.append(
            StructureViolation(
                "unclassified_example_python_file",
                path,
                "add an explicit catalog entry with its classification",
            )
        )
    for path in sorted(catalog_paths - discovered_paths):
        if path not in {
            Path(entry.get("path", ""))
            for entry in entries
            if entry.get("classification") == "generated"
        }:
            violations.append(
                StructureViolation(
                    "catalog_non_python_file",
                    path,
                    "catalog entry must correspond to a non-generated Python file",
                )
            )

    for entry in historical_entries:
        canonical_id = entry.get("canonical_id")
        path = Path(str(entry.get("path")))
        canonical = entries_by_id.get(canonical_id) if isinstance(canonical_id, str) else None
        if canonical is None or canonical.get("compatibility") != "canonical":
            violations.append(
                StructureViolation(
                    "invalid_example_compatibility_target",
                    path,
                    "historical entry point must reference one canonical_id",
                )
            )

    for tier in ("fast", "extended", "release"):
        if not smoke_ids[tier]:
            violations.append(
                StructureViolation(
                    "empty_example_smoke_tier",
                    EXAMPLE_CATALOG_PATH,
                    f"smoke tier `{tier}` must contain at least one entry",
                )
            )
    missing_fast_ids = sorted(EXAMPLE_REQUIRED_FAST_IDS - smoke_ids["fast"])
    if missing_fast_ids:
        violations.append(
            StructureViolation(
                "incomplete_fast_example_smoke_coverage",
                EXAMPLE_CATALOG_PATH,
                f"fast tier is missing: {', '.join(missing_fast_ids)}",
            )
        )
    return violations


def _audit_generated_example_output_policy(repo_root: Path) -> list[StructureViolation]:
    if not (repo_root / "examples").exists():
        return []
    if "examples/output/" in _gitignore_entries(repo_root):
        return []
    return [
        StructureViolation(
            "generated_example_output_policy",
            Path(".gitignore"),
            "add `examples/output/` so generated example files are not treated as source",
        )
    ]


def _audit_generated_ignore_entries(repo_root: Path) -> list[StructureViolation]:
    ignored_entries = _gitignore_entries(repo_root)
    missing = sorted(EXPECTED_GENERATED_IGNORE_ENTRIES - ignored_entries - {"examples/output/"})
    return [
        StructureViolation(
            "generated_artifact_ignore_policy",
            Path(".gitignore"),
            f"add `{entry}` to ignore generated artifacts and caches",
        )
        for entry in missing
    ]


def _maturin_include_patterns(repo_root: Path) -> list[str]:
    manifest_path = repo_root / "pyproject.toml"
    if not manifest_path.is_file():
        return []
    try:
        manifest = tomllib.loads(manifest_path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return []
    tool = manifest.get("tool")
    maturin = tool.get("maturin") if isinstance(tool, dict) else None
    includes = maturin.get("include") if isinstance(maturin, dict) else None
    return (
        [pattern for pattern in includes if isinstance(pattern, str)]
        if isinstance(includes, list)
        else []
    )


def _audit_maturin_include_patterns(repo_root: Path) -> list[StructureViolation]:
    violations: list[StructureViolation] = []
    for pattern in sorted(_maturin_include_patterns(repo_root)):
        try:
            matches = [
                path
                for path in repo_root.glob(pattern)
                if path.is_file() and _is_within_repo(repo_root, path.resolve())
            ]
        except (OSError, ValueError):
            matches = []
        if not matches:
            violations.append(
                StructureViolation(
                    "maturin_include_no_matches",
                    Path("pyproject.toml"),
                    (
                        f"`tool.maturin.include` glob `{pattern}` matches no files "
                        "inside the repository"
                    ),
                )
            )
    return violations


def _iter_cargo_manifests(repo_root: Path) -> list[Path]:
    return sorted(
        path
        for path in repo_root.rglob("Cargo.toml")
        if path.is_file() and not _is_ignored_relative_path(_display_path(repo_root, path))
    )


def _cargo_dependency_specs(
    manifest: Mapping[str, object],
) -> list[tuple[str, Mapping[str, object]]]:
    dependencies: list[tuple[str, Mapping[str, object]]] = []

    def add_dependency_specs(value: Mapping[object, object]) -> None:
        for dependency_name, specification in value.items():
            if isinstance(dependency_name, str) and isinstance(specification, Mapping):
                dependencies.append((dependency_name, specification))

    def visit(value: object, key: str | None = None, patch_registry: bool = False) -> None:
        if not isinstance(value, Mapping):
            return
        if (
            key is not None
            and (key == "dependencies" or key.endswith("-dependencies"))
            or key == "replace"
            or patch_registry
        ):
            add_dependency_specs(value)
        for child_key, child_value in value.items():
            if isinstance(child_key, str):
                visit(child_value, child_key, patch_registry=key == "patch")

    visit(manifest)
    return dependencies


def _cargo_package_name(manifest_path: Path) -> str | None:
    try:
        manifest = tomllib.loads(manifest_path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    package = manifest.get("package")
    name = package.get("name") if isinstance(package, dict) else None
    return name if isinstance(name, str) else None


def _audit_local_cargo_dependencies(repo_root: Path) -> list[StructureViolation]:
    violations: list[StructureViolation] = []
    allowed_targets = {"gummy_canvas": frozenset({"gummy_ecs", "gummy_synth"})}
    downstream_fixture_manifest = Path("tests/fixtures/rust/downstream_runtime_api/Cargo.toml")
    downstream_fixture_targets = frozenset({"gummy_canvas", "gummy_ecs", "gummy_synth"})
    for manifest_path in _iter_cargo_manifests(repo_root):
        try:
            manifest = tomllib.loads(manifest_path.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            continue
        source_name = _cargo_package_name(manifest_path)
        for dependency_name, specification in _cargo_dependency_specs(manifest):
            dependency_path = specification.get("path")
            if not isinstance(dependency_path, str):
                continue
            resolved_path = (manifest_path.parent / dependency_path).resolve()
            relative_manifest = _display_path(repo_root, manifest_path)
            if not _is_within_repo(repo_root, resolved_path):
                violations.append(
                    StructureViolation(
                        "cargo_path_dependency_outside_repo",
                        relative_manifest,
                        (
                            f"local dependency `{dependency_name}` resolves outside "
                            f"the repository: `{dependency_path}`"
                        ),
                    )
                )
                continue
            target_name = specification.get("package", dependency_name)
            target_manifest = resolved_path / "Cargo.toml"
            target_package_name = _cargo_package_name(target_manifest)
            if target_package_name is not None:
                target_name = target_package_name
            if not isinstance(source_name, str) or not isinstance(target_name, str):
                continue
            allowed = allowed_targets.get(source_name, frozenset())
            if relative_manifest == downstream_fixture_manifest:
                allowed = downstream_fixture_targets
            if target_name not in allowed:
                violations.append(
                    StructureViolation(
                        "cargo_local_dependency_not_allowed",
                        relative_manifest,
                        f"`{source_name}` may not have a local dependency on `{target_name}`",
                    )
                )
    return violations


def _command_paths(command: str) -> set[Path]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;()<>")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    paths: set[Path] = set()
    for token in tokens:
        candidate = token.rstrip(",;:")
        if candidate.startswith(("scripts/", "examples/")):
            paths.add(Path(candidate))
    return paths


def _make_recipe_commands(makefile: Path) -> list[str]:
    if not makefile.is_file():
        return []
    return [
        line[1:]
        for line in makefile.read_text(errors="ignore").splitlines()
        if line.startswith("\t")
    ]


def _workflow_run_commands(workflow: Path) -> list[str]:
    commands: list[str] = []
    lines = workflow.read_text(errors="ignore").splitlines()
    index = 0
    while index < len(lines):
        match = WORKFLOW_RUN_RE.match(lines[index])
        if match is None:
            index += 1
            continue
        command = match.group("command").strip()
        indent = len(match.group("indent"))
        if command in {"|", ">", "|-", ">-", "|+", ">+"}:
            index += 1
            block_lines: list[str] = []
            while index < len(lines):
                line = lines[index]
                if line.strip() and len(line) - len(line.lstrip()) <= indent:
                    break
                block_lines.append(line)
                index += 1
            commands.append("\n".join(block_lines))
            continue
        commands.append(command)
        index += 1
    return commands


def _audit_recipe_paths(repo_root: Path) -> list[StructureViolation]:
    commands: list[tuple[Path, str]] = []
    makefile = repo_root / "Makefile"
    commands.extend((Path("Makefile"), command) for command in _make_recipe_commands(makefile))
    workflows = repo_root / ".github/workflows"
    if workflows.is_dir():
        for workflow in sorted((*workflows.glob("*.yml"), *workflows.glob("*.yaml"))):
            relative = _display_path(repo_root, workflow)
            commands.extend((relative, command) for command in _workflow_run_commands(workflow))

    violations: list[StructureViolation] = []
    for command_path, command in commands:
        for referenced_path in sorted(_command_paths(command)):
            target = (repo_root / referenced_path).resolve()
            if _is_within_repo(repo_root, target) and target.exists():
                continue
            violations.append(
                StructureViolation(
                    "missing_recipe_path",
                    command_path,
                    f"recipe path `{referenced_path}` does not exist",
                )
            )
    return violations


def _tracked_paths(repo_root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            check=False,
            capture_output=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return sorted(
        Path(path) for path in result.stdout.decode(errors="surrogateescape").split("\0") if path
    )


def _is_generated_tracked_path(path: Path) -> bool:
    if any(part in CACHE_DIRECTORY_NAMES for part in path.parts):
        return True
    if any(part in ROOT_GENERATED_DIRECTORY_NAMES for part in path.parts):
        return True
    if path == Path("examples/output") or Path("examples/output") in path.parents:
        return True
    if (
        path.name == "coverage.xml"
        or path.name == ".coverage"
        or path.name.startswith(".coverage.")
    ):
        return True
    return path.suffix.lower() in COMPILED_ARTIFACT_SUFFIXES


def _audit_tracked_generated_artifacts(repo_root: Path) -> list[StructureViolation]:
    return [
        StructureViolation(
            "tracked_generated_artifact",
            path,
            "generated, cache, compiled extension, or coverage artifact must not be git-tracked",
        )
        for path in _tracked_paths(repo_root)
        if _is_generated_tracked_path(path)
    ]


def _audit_rust_hubs(repo_root: Path) -> list[StructureViolation]:
    violations: list[StructureViolation] = []
    for relative_root in _workspace_member_source_roots(repo_root):
        root = repo_root / relative_root
        if not root.exists():
            continue
        for path in root.rglob("*.rs"):
            relative = _display_path(repo_root, path)
            if _is_ignored_relative_path(relative):
                continue
            if path.with_suffix("").is_dir() and relative not in DOCUMENTED_RUST_HUBS:
                violations.append(
                    StructureViolation(
                        "undocumented_rust_hub",
                        relative,
                        (
                            "same-stem Rust file+directory hubs must be documented in "
                            "`structure_audit.py` and contributor docs"
                        ),
                    )
                )

    for relative_path in sorted(DOCUMENTED_RUST_HUBS):
        path = repo_root / relative_path
        if path.is_file() and path.with_suffix("").is_dir():
            continue
        violations.append(
            StructureViolation(
                "stale_documented_rust_hub",
                relative_path,
                (
                    "documented Rust hubs must retain both the `.rs` file and its "
                    "same-stem directory"
                ),
            )
        )
    return violations


def audit(repo_root: Path = Path(".")) -> list[StructureViolation]:
    root = repo_root.resolve()
    violations: list[StructureViolation] = []
    violations.extend(_audit_python_sibling_packages(root))
    violations.extend(_audit_python_support_prefix_clusters(root))
    violations.extend(_audit_source_testing_package(root))
    violations.extend(_audit_obsolete_source_packages(root))
    violations.extend(_audit_stale_text_references(root))
    violations.extend(_audit_local_markdown_links(root))
    violations.extend(_audit_backticked_repository_paths(root))
    violations.extend(_audit_maturin_include_patterns(root))
    violations.extend(_audit_local_cargo_dependencies(root))
    violations.extend(_audit_recipe_paths(root))
    violations.extend(_audit_example_catalog(root))
    violations.extend(_audit_generated_example_output_policy(root))
    violations.extend(_audit_generated_ignore_entries(root))
    violations.extend(_audit_tracked_generated_artifacts(root))
    violations.extend(_audit_rust_hubs(root))
    return sorted(violations, key=lambda item: (item.code, str(item.path), item.message))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo_root",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root to audit. Defaults to the current working directory.",
    )
    args = parser.parse_args()

    violations = audit(args.repo_root)
    for violation in violations:
        print(f"{violation.code:32} {violation.path}  # {violation.message}")
    if violations:
        print(f"STRUCTURE_VIOLATIONS {len(violations)}")
        return 1
    print("STRUCTURE_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
