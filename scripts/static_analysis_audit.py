#!/usr/bin/env python3
"""Enforce the reviewed Python static-analysis exception inventory.

The manifest deliberately records every checker exclusion, Ruff per-file ignore,
and inline suppression. It is a no-new-suppression ratchet: configuration or
source changes that add an unowned suppression fail until a maintainer reviews
and records its owner, rationale, and focused behavior check.
"""

from __future__ import annotations

import argparse
import io
import re
import tokenize
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST_PATH = Path("docs/contribute/static_analysis_exceptions.toml")
PYPROJECT_PATH = Path("pyproject.toml")
UNDEFINED_NAME_CODES = frozenset({"F811", "F821", "F822"})
SUPPRESSION_RE = re.compile(
    r"#\s*(?:(?P<type_tool>type|pyright):\s*ignore(?:\[(?P<type_codes>[^\]]+)\])?"
    r"|noqa(?::\s*(?P<noqa_codes>[A-Z]+\d+(?:\s*,\s*[A-Z]+\d+)*))?)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class StaticAnalysisViolation:
    """One deterministic static-analysis manifest finding."""

    code: str
    location: str
    message: str


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return value


def _metadata_violations(entry: object, location: str) -> list[StaticAnalysisViolation]:
    if not isinstance(entry, dict):
        return [
            StaticAnalysisViolation("invalid_exception", location, "entry must be a TOML table")
        ]
    violations: list[StaticAnalysisViolation] = []
    for field in ("owner", "reason"):
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            violations.append(
                StaticAnalysisViolation(
                    "missing_exception_metadata", location, f"`{field}` must be a non-empty string"
                )
            )
    checks = _string_list(entry.get("checks"))
    if not checks:
        violations.append(
            StaticAnalysisViolation(
                "missing_exception_metadata", location, "`checks` must be a non-empty string list"
            )
        )
    return violations


def _entries(document: dict[str, Any], name: str) -> list[dict[str, Any]]:
    value = document.get(name, [])
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def _inline_suppressions(
    repo_root: Path, roots: list[str]
) -> set[tuple[str, int, str, tuple[str, ...]]]:
    found: set[tuple[str, int, str, tuple[str, ...]]] = set()
    for root_name in roots:
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            relative_path = path.relative_to(repo_root).as_posix()
            tokens = tokenize.generate_tokens(
                io.StringIO(path.read_text(encoding="utf-8")).readline
            )
            for token in tokens:
                if token.type != tokenize.COMMENT:
                    continue
                match = SUPPRESSION_RE.search(token.string)
                if match is None:
                    continue
                tool = match.group("type_tool") or "noqa"
                codes = match.group("type_codes") or match.group("noqa_codes") or "all"
                normalized_codes = tuple(
                    sorted(code.strip() for code in codes.split(",") if code.strip())
                )
                found.add((relative_path, token.start[0], tool.lower(), normalized_codes))
    return found


def _manifest_inline_suppressions(
    document: dict[str, Any], violations: list[StaticAnalysisViolation]
) -> set[tuple[str, int, str, tuple[str, ...]]]:
    found: set[tuple[str, int, str, tuple[str, ...]]] = set()
    entries = document.get("inline_suppressions", [])
    if not isinstance(entries, list):
        violations.append(
            StaticAnalysisViolation(
                "invalid_inline_suppressions", "inline_suppressions", "must be an array of tables"
            )
        )
        return found
    for index, entry in enumerate(entries):
        location = f"inline_suppressions[{index}]"
        violations.extend(_metadata_violations(entry, location))
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        line = entry.get("line")
        tool = entry.get("tool")
        codes = _string_list(entry.get("codes"))
        if (
            not isinstance(path, str)
            or not isinstance(line, int)
            or not isinstance(tool, str)
            or not codes
        ):
            violations.append(
                StaticAnalysisViolation(
                    "invalid_inline_suppression",
                    location,
                    "path, line, tool, and non-empty codes are required",
                )
            )
            continue
        key = (path, line, tool.lower(), tuple(sorted(codes)))
        if key in found:
            violations.append(
                StaticAnalysisViolation(
                    "duplicate_inline_suppression", location, "suppression is listed more than once"
                )
            )
        found.add(key)
    return found


def _type_check_exceptions(
    document: dict[str, Any], violations: list[StaticAnalysisViolation]
) -> set[tuple[str, str]]:
    expected: set[tuple[str, str]] = set()
    entries = document.get("type_check_exceptions", [])
    if not isinstance(entries, list):
        violations.append(
            StaticAnalysisViolation(
                "invalid_type_check_exceptions",
                "type_check_exceptions",
                "must be an array of tables",
            )
        )
        return expected
    for index, entry in enumerate(entries):
        location = f"type_check_exceptions[{index}]"
        violations.extend(_metadata_violations(entry, location))
        if not isinstance(entry, dict):
            continue
        tool = entry.get("tool")
        path = entry.get("path")
        removal_pbi = entry.get("removal_pbi")
        if tool not in {"mypy", "basedpyright"} or not isinstance(path, str):
            violations.append(
                StaticAnalysisViolation(
                    "invalid_type_check_exception",
                    location,
                    "tool and exact source-file path are required",
                )
            )
            continue
        if any(character in path for character in "*?["):
            violations.append(
                StaticAnalysisViolation(
                    "broad_type_check_exception",
                    location,
                    "type checker exceptions must name one file",
                )
            )
        if not isinstance(removal_pbi, str) or not removal_pbi.strip():
            violations.append(
                StaticAnalysisViolation(
                    "missing_removal_pbi", location, "temporary exception must name its removal PBI"
                )
            )
        expected.add((tool, path))
    return expected


def _ruff_ignores(
    document: dict[str, Any], violations: list[StaticAnalysisViolation]
) -> dict[str, tuple[str, ...]]:
    expected: dict[str, tuple[str, ...]] = {}
    entries = document.get("ruff_ignores", [])
    if not isinstance(entries, list):
        violations.append(
            StaticAnalysisViolation(
                "invalid_ruff_ignores", "ruff_ignores", "must be an array of tables"
            )
        )
        return expected
    for index, entry in enumerate(entries):
        location = f"ruff_ignores[{index}]"
        violations.extend(_metadata_violations(entry, location))
        if not isinstance(entry, dict):
            continue
        pattern = entry.get("pattern")
        codes = _string_list(entry.get("codes"))
        if not isinstance(pattern, str) or not codes:
            violations.append(
                StaticAnalysisViolation(
                    "invalid_ruff_ignore", location, "pattern and non-empty codes are required"
                )
            )
            continue
        if pattern in expected:
            violations.append(
                StaticAnalysisViolation(
                    "duplicate_ruff_ignore", location, "pattern is listed more than once"
                )
            )
        code_set = tuple(sorted(codes))
        if UNDEFINED_NAME_CODES.intersection(code_set) and any(token in pattern for token in "*?["):
            violations.append(
                StaticAnalysisViolation(
                    "broad_undefined_name_ignore",
                    location,
                    "F811/F821/F822 ignores must name one exact file",
                )
            )
        if UNDEFINED_NAME_CODES.intersection(code_set):
            removal_pbi = entry.get("removal_pbi")
            if not isinstance(removal_pbi, str) or not removal_pbi.strip():
                violations.append(
                    StaticAnalysisViolation(
                        "missing_removal_pbi",
                        location,
                        "temporary undefined-name ignore needs its removal PBI",
                    )
                )
        expected[pattern] = code_set
    return expected


def _configuration_violations(
    repo_root: Path,
    expected_type_exceptions: set[tuple[str, str]],
    expected_ruff_ignores: dict[str, tuple[str, ...]],
) -> list[StaticAnalysisViolation]:
    config_path = repo_root / PYPROJECT_PATH
    if not config_path.is_file():
        return [
            StaticAnalysisViolation("missing_pyproject", str(PYPROJECT_PATH), "file does not exist")
        ]
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        return [StaticAnalysisViolation("invalid_pyproject", str(PYPROJECT_PATH), str(error))]

    tool = config.get("tool", {})
    mypy = tool.get("mypy", {}) if isinstance(tool, dict) else {}
    basedpyright = tool.get("basedpyright", {}) if isinstance(tool, dict) else {}
    ruff = tool.get("ruff", {}) if isinstance(tool, dict) else {}
    actual_mypy = set()
    for pattern in _string_list(mypy.get("exclude")) or []:
        if pattern.startswith("^") and pattern.endswith("$"):
            actual_mypy.add(("mypy", re.sub(r"\\(.)", r"\1", pattern[1:-1])))
        else:
            actual_mypy.add(("mypy", pattern))
    actual_basedpyright = {
        ("basedpyright", path) for path in _string_list(basedpyright.get("exclude")) or []
    }
    actual_type_exceptions = actual_mypy | actual_basedpyright
    violations: list[StaticAnalysisViolation] = []
    if actual_type_exceptions != expected_type_exceptions:
        violations.append(
            StaticAnalysisViolation(
                "type_check_exception_drift",
                str(PYPROJECT_PATH),
                (
                    f"configured={sorted(actual_type_exceptions)} "
                    f"manifest={sorted(expected_type_exceptions)}"
                ),
            )
        )

    lint = ruff.get("lint", {}) if isinstance(ruff, dict) else {}
    actual_ruff = lint.get("per-file-ignores", {}) if isinstance(lint, dict) else {}
    normalized_ruff: dict[str, tuple[str, ...]] = {}
    if isinstance(actual_ruff, dict):
        for pattern, raw_codes in actual_ruff.items():
            codes = _string_list(raw_codes)
            if isinstance(pattern, str) and codes is not None:
                normalized_ruff[pattern] = tuple(sorted(codes))
    if normalized_ruff != expected_ruff_ignores:
        violations.append(
            StaticAnalysisViolation(
                "ruff_ignore_drift",
                str(PYPROJECT_PATH),
                "every Ruff per-file ignore must be represented exactly in the manifest",
            )
        )
    for pattern, codes in normalized_ruff.items():
        if UNDEFINED_NAME_CODES.intersection(codes) and any(token in pattern for token in "*?["):
            violations.append(
                StaticAnalysisViolation(
                    "broad_undefined_name_ignore",
                    pattern,
                    "F811/F821/F822 ignores must name one exact file",
                )
            )
    return violations


def audit(
    repo_root: Path = Path("."), manifest_path: Path | None = None
) -> list[StaticAnalysisViolation]:
    """Return all unowned or broadened static-analysis suppressions."""

    root = repo_root.resolve()
    path = (root / DEFAULT_MANIFEST_PATH if manifest_path is None else manifest_path).resolve()
    if not path.is_file():
        return [
            StaticAnalysisViolation(
                "missing_manifest", str(path), "exception manifest does not exist"
            )
        ]
    try:
        document: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        return [StaticAnalysisViolation("invalid_manifest", str(path), str(error))]

    violations: list[StaticAnalysisViolation] = []
    manifest = document.get("manifest")
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        violations.append(
            StaticAnalysisViolation("invalid_manifest_metadata", "manifest", "version must be 1")
        )
        roots: list[str] = []
    else:
        roots = _string_list(manifest.get("roots")) or []
        if not roots:
            violations.append(
                StaticAnalysisViolation(
                    "invalid_manifest_metadata", "manifest.roots", "must list scanned Python roots"
                )
            )

    expected_type_exceptions = _type_check_exceptions(document, violations)
    expected_ruff_ignores = _ruff_ignores(document, violations)
    expected_inline = _manifest_inline_suppressions(document, violations)
    actual_inline = _inline_suppressions(root, roots)
    for suppression in sorted(actual_inline - expected_inline):
        violations.append(
            StaticAnalysisViolation(
                "unowned_inline_suppression",
                f"{suppression[0]}:{suppression[1]}",
                f"{suppression[2]} {', '.join(suppression[3])} is absent from the manifest",
            )
        )
    for suppression in sorted(expected_inline - actual_inline):
        violations.append(
            StaticAnalysisViolation(
                "stale_inline_suppression",
                f"{suppression[0]}:{suppression[1]}",
                "manifest entry no longer matches a source suppression",
            )
        )
    violations.extend(
        _configuration_violations(root, expected_type_exceptions, expected_ruff_ignores)
    )
    return sorted(violations, key=lambda item: (item.code, item.location, item.message))


def main(argv: list[str] | None = None) -> int:
    """Run the static-analysis suppression ratchet."""

    parser = argparse.ArgumentParser(description="Validate static-analysis exception ownership.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Manifest path relative to cwd.",
    )
    args = parser.parse_args(argv)
    violations = audit(Path("."), args.manifest)
    if not violations:
        print("STATIC_ANALYSIS_CHECK PASSED")
        return 0
    print("STATIC_ANALYSIS_CHECK FAILED")
    for violation in violations:
        print(f"  {violation.code}: {violation.location}  # {violation.message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
