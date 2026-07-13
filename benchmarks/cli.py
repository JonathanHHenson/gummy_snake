"""Small governance-first CLI for static catalog and database administration."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter_ns

from .framework.git_database.audit import audit_database
from .framework.git_database.store import GitBenchmarkDatabase
from .framework.modes import record_head, worktree
from .framework.runner import BenchmarkRecorderRunner, compare_record_to_baseline
from .governance import ExecutionClass, GovernanceError, reject_authority_overrides
from .schema.catalog import Catalog, CatalogError, load_catalog
from .schema.records import BenchmarkRecord


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


def _dispatch_smoke(catalog: Catalog) -> list[dict[str, object]]:
    """Run each static headless workload once through its registered suite dispatcher.

    This command is intentionally non-authoritative: it performs no baseline lookup,
    comparison, build, or database write. Interactive/device workloads are excluded
    rather than being downgraded to headless execution.
    """

    from .suites.registry import dispatch

    results: list[dict[str, object]] = []
    for workload in catalog.workloads:
        if workload.execution_class is not ExecutionClass.HEADLESS:
            continue
        start = perf_counter_ns()
        run = dispatch(
            workload.suite_id,
            workload.id,
            workload.parameters,
            workload.execution_class,
        )
        elapsed_ns = perf_counter_ns() - start
        results.append(
            {
                "suite": workload.suite_id,
                "workload": workload.id,
                "case": workload.case_id,
                "elapsed_ns": elapsed_ns,
                "execution_class": workload.execution_class.value,
                **dict(run.summary),
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
            for result in _dispatch_smoke(catalog):
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
        catalog = load_catalog(namespace.catalog)
        runner = BenchmarkRecorderRunner(namespace.repo, catalog, namespace.output)

        def compare(baseline: object, candidate: BenchmarkRecord):
            return compare_record_to_baseline(catalog, baseline, candidate)

        if namespace.command == "worktree":
            mode_result = worktree(database, runner, compare)
        elif namespace.command == "record-head":
            mode_result = record_head(database, runner, compare)
        else:  # argparse owns the command set; retain a fail-closed guard for direct calls.
            raise RuntimeError(f"unsupported benchmark command: {namespace.command}")
        print(f"{mode_result.mode.value}: {mode_result.outcome.value}: {mode_result.reason}")
        if mode_result.candidate_branch and mode_result.candidate_commit:
            print(
                f"staged candidate: {mode_result.candidate_branch} @ {mode_result.candidate_commit}"
            )
        return 0 if mode_result.outcome.value.startswith("pass") else 1
    except (CatalogError, GovernanceError, RuntimeError, ValueError) as error:
        print(f"benchmark: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised through scripts/benchmark.py
    raise SystemExit(main())
