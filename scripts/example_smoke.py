#!/usr/bin/env python3
"""Run catalog-defined bounded example smoke tiers without creating output files."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

CATALOG_PATH = Path("examples/example_catalog.toml")
TIER_ORDER = {"fast": 0, "extended": 1, "release": 2}
ENTRY_CLASSIFICATIONS = {"entry_point"}


def _load_catalog(repo_root: Path) -> list[dict[str, object]]:
    catalog_path = repo_root / CATALOG_PATH
    with catalog_path.open("rb") as catalog_file:
        catalog = tomllib.load(catalog_file)
    entries = catalog.get("files")
    if not isinstance(entries, list):
        raise ValueError(f"{CATALOG_PATH} must define [[files]] entries")
    if not all(isinstance(entry, dict) for entry in entries):
        raise ValueError(f"{CATALOG_PATH} entries must be tables")
    return entries


def _selected_entries(entries: list[dict[str, object]], tier: str) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for entry in entries:
        if entry.get("classification") not in ENTRY_CLASSIFICATIONS:
            continue
        smoke_tier = entry.get("smoke_tier")
        if not isinstance(smoke_tier, str) or smoke_tier not in TIER_ORDER:
            continue
        if TIER_ORDER[smoke_tier] <= TIER_ORDER[tier]:
            selected.append(entry)
    return sorted(selected, key=lambda entry: str(entry["path"]))


def _command(entry: dict[str, object]) -> list[str]:
    path = entry["path"]
    args = entry["smoke_args"]
    if (
        not isinstance(path, str)
        or not isinstance(args, list)
        or not all(isinstance(argument, str) for argument in args)
    ):
        raise ValueError(f"invalid smoke command entry: {entry!r}")
    if "--no-save" not in args:
        raise ValueError(f"smoke entry must include --no-save: {path}")
    capabilities = entry.get("capabilities")
    if isinstance(capabilities, list) and "synth" in capabilities and "--no-play" not in args:
        raise ValueError(f"synth smoke entry must include --no-play: {path}")
    return [sys.executable, path, *args]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=sorted(TIER_ORDER), required=True)
    parser.add_argument("--list", action="store_true", help="list commands without running them")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root; defaults to the parent of scripts/",
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()

    try:
        entries = _selected_entries(_load_catalog(repo_root), args.tier)
        commands = [_command(entry) for entry in entries]
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"EXAMPLE_SMOKE_INVALID {error}")
        return 2

    if not commands:
        print(f"EXAMPLE_SMOKE_EMPTY tier={args.tier}")
        return 2

    for command in commands:
        print(f"EXAMPLE_SMOKE_COMMAND {' '.join(command)}")
        if args.list:
            continue
        result = subprocess.run(command, cwd=repo_root, check=False)
        if result.returncode:
            print(f"EXAMPLE_SMOKE_FAILED tier={args.tier} exit={result.returncode}")
            return result.returncode

    if args.list:
        print(f"EXAMPLE_SMOKE_LISTED tier={args.tier} count={len(commands)}")
    else:
        print(f"EXAMPLE_SMOKE_OK tier={args.tier} count={len(commands)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
