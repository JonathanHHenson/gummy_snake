#!/usr/bin/env python3
"""Audit source-tree organization conventions for Gummy Snake.

This is intentionally lightweight: it catches naming/layout regressions that are
confusing for navigation but do not require running the full test suite.
"""

from __future__ import annotations

import argparse
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "target",
}
IGNORED_RELATIVE_DIRS = (Path("examples/output"),)
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
    Path("tests/unit/test_structure_audit.py"),
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
SUPPORT_CLUSTER_DIRECTORIES = (Path("tests/helpers"), Path("tests/benchmark"))
INTENTIONAL_SUPPORT_PREFIX_CLUSTERS = {
    Path("tests/helpers"): frozenset({"rust_canvas"}),
    Path("tests/benchmark"): frozenset({"canvas_backend_perf_scene"}),
}
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
    "rust_canvas_context_helpers": "use `tests.helpers.rust_canvas_context` instead",
    "rust_canvas_asset_fakes": "use `tests.helpers.rust_canvas_assets` instead",
    "rust_canvas_image_fakes": "use `tests.helpers.rust_canvas_image_kernels` instead",
    "rust_canvas_state_fakes": "use `tests.helpers.rust_canvas_state` instead",
    "webgl_helpers": "use `tests.helpers.webgl` instead",
    "gummysnake.events.input_state": "use `gummysnake.core.input_events` instead",
    "gummysnake.events.input_events": "use `gummysnake.core.input_events` instead",
}
DOCUMENTED_RUST_HUBS = {
    Path("crates/gummy_canvas/src/bindings.rs"),
    Path("crates/gummy_canvas/src/bindings/ecs.rs"),
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
    Path("crates/gummy_ecs/src/execution/direct_point_hash_grid.rs"),
    Path("crates/gummy_ecs/src/execution/f64_program.rs"),
    Path("crates/gummy_ecs/src/execution/tests.rs"),
    Path("crates/gummy_ecs/src/plan.rs"),
    Path("crates/gummy_ecs/src/spatial.rs"),
    Path("crates/gummy_ecs/src/spatial/hash_grid.rs"),
    Path("crates/gummy_ecs/src/tree_spatial.rs"),
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
                candidate = match.group("content").split(maxsplit=1)[0]
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


def _audit_generated_example_output_policy(repo_root: Path) -> list[StructureViolation]:
    if not (repo_root / "examples").exists():
        return []
    gitignore = repo_root / ".gitignore"
    ignored = False
    if gitignore.exists():
        ignored = "examples/output/" in gitignore.read_text(errors="ignore").splitlines()
    if ignored:
        return []
    return [
        StructureViolation(
            "generated_example_output_policy",
            Path(".gitignore"),
            "add `examples/output/` so generated example files are not treated as source",
        )
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
    violations.extend(_audit_generated_example_output_policy(root))
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
