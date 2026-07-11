"""Small governance-first CLI for static catalog and database administration."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter_ns

from .framework.database import GitBenchmarkDatabase, audit_database
from .governance import ExecutionClass, GovernanceError, reject_authority_overrides
from .schema.catalog import Catalog, CatalogError, load_catalog
from .worker.provenance import release_build_plan


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark", description="Gummy Snake governed benchmark framework"
    )
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="code repository (default: current directory)"
    )
    parser.add_argument(
        "--remote", help="configured authoritative data remote name or URL; ref remains fixed"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("worktree", "record-head"):
        command = commands.add_parser(name)
        command.add_argument("catalog", type=Path, help="static TOML catalog")
        command.add_argument("--output", type=Path, default=Path(".scratch/benchmark/build"))
    audit = commands.add_parser("audit")
    audit.add_argument(
        "--json", action="store_true", help="reserved for machine-readable audit output"
    )
    catalog = commands.add_parser("catalog")
    catalog.add_argument("catalog", type=Path, help="static TOML catalog")
    smoke = commands.add_parser(
        "smoke",
        help="run every static headless workload once without comparison or database writes",
    )
    smoke.add_argument("catalog", type=Path, help="static TOML catalog")
    return parser


def _dispatch_canvas_smoke(catalog: Catalog) -> list[dict[str, object]]:
    """Run each static Canvas headless workload once through its production dispatcher.

    This command is intentionally non-authoritative: it performs no baseline lookup,
    comparison, build, or database write. Native-interactive workloads are excluded
    rather than being downgraded to headless execution.
    """

    if any(workload.suite_id != "canvas" for workload in catalog.workloads):
        raise CatalogError("the smoke command currently supports only the static canvas suite")
    from .suites.canvas import dispatch

    results: list[dict[str, object]] = []
    for workload in catalog.workloads:
        if workload.execution_class is not ExecutionClass.HEADLESS:
            continue
        start = perf_counter_ns()
        run = dispatch(workload.id, workload.parameters, workload.execution_class)
        elapsed_ns = perf_counter_ns() - start
        results.append(
            {
                "workload": workload.id,
                "case": workload.case_id,
                "elapsed_ns": elapsed_ns,
                "frames": run.frame_count,
                "pixel_bytes": len(run.pixels),
                "execution_class": workload.execution_class.value,
            }
        )
    if not results:
        raise CatalogError("smoke requires at least one static headless workload")
    return results


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        reject_authority_overrides(arguments)
    except GovernanceError as error:
        print(f"benchmark: error: {error}", file=sys.stderr)
        return 2
    parser = _parser()
    namespace = parser.parse_args(arguments)
    try:
        if namespace.command == "catalog":
            catalog = load_catalog(namespace.catalog)
            print(f"catalog {catalog.path}: {len(catalog.workloads)} static workloads")
            print(f"digest {catalog.digest}")
            return 0
        if namespace.command == "smoke":
            catalog = load_catalog(namespace.catalog)
            for result in _dispatch_canvas_smoke(catalog):
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0
        database = GitBenchmarkDatabase(namespace.repo)
        if namespace.remote:
            database.fetch_authoritative_ref(namespace.remote)
        if namespace.command == "audit":
            issues = audit_database(database)
            if issues:
                for issue in issues:
                    print(f"{issue.path}: {issue.message}", file=sys.stderr)
                return 1
            print("benchmark database audit passed")
            return 0
        # Planning is safe to expose, but actual execution needs a suite-owned isolated
        # worker dispatcher. The shared layer must not substitute source imports or a fake runner.
        catalog = load_catalog(namespace.catalog)
        plan = release_build_plan(namespace.repo, namespace.output)
        print(f"{namespace.command}: catalog {catalog.digest}", file=sys.stderr)
        print(f"planned release build: {' '.join(plan.command)}", file=sys.stderr)
        print("benchmark: no suite worker dispatcher is registered", file=sys.stderr)
        print("refusing to run a synthetic fallback", file=sys.stderr)
        return 3
    except (CatalogError, GovernanceError, RuntimeError, ValueError) as error:
        print(f"benchmark: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised through scripts/benchmark.py
    raise SystemExit(main())
