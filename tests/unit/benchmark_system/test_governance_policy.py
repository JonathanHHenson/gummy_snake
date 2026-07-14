from __future__ import annotations

from decimal import Decimal

import pytest

import benchmarks
import benchmarks.governance as governance
from benchmarks.governance import (
    EXECUTION_CLASS_POLICIES,
    LOCAL_DATABASE_POLICY,
    LOCAL_HISTORY_DIRECTORY,
    MODE_POLICIES,
    PERCENT_REGRESSION_LIMIT,
    PRODUCTION_DOMAINS,
    REGRESSION_LIMIT_FRACTION,
    REGRESSION_LIMIT_PERCENT,
    BenchmarkDomain,
    BenchmarkMode,
    ExecutionClass,
    GovernanceError,
    degradation_exceeds_limit,
    reject_policy_overrides,
)


def test_only_local_benchmark_policy_is_exported_and_selectable() -> None:
    assert benchmarks.__all__ == [
        "DEFAULT_LOCAL_HISTORY",
        "LocalBenchmarkDatabase",
        "PERCENT_REGRESSION_LIMIT",
    ]
    assert {execution_class.value for execution_class in ExecutionClass} == {
        "headless",
        "simulated-realtime",
        "native-interactive",
        "native-audio",
    }
    assert set(governance.__all__) == {
        "EXECUTION_CLASS_POLICIES",
        "GOVERNANCE_VERSION",
        "LOCAL_DATABASE_POLICY",
        "LOCAL_HISTORY_DIRECTORY",
        "MODE_POLICIES",
        "PERCENT_REGRESSION_LIMIT",
        "PRODUCTION_DOMAIN_INVENTORY",
        "PRODUCTION_DOMAINS",
        "REGRESSION_LIMIT_FRACTION",
        "REGRESSION_LIMIT_PERCENT",
        "BenchmarkDomain",
        "BenchmarkMode",
        "CapabilityError",
        "DomainInventoryEntry",
        "ExecutionClass",
        "ExecutionClassPolicy",
        "GovernanceError",
        "LocalDatabasePolicy",
        "ModePolicy",
        "capability_error",
        "degradation_exceeds_limit",
        "reject_policy_overrides",
    }


def test_fixed_policy_bypass_flags_are_rejected() -> None:
    for argument in ("--threshold=0.02", "--regression-limit", "--force-record"):
        with pytest.raises(GovernanceError, match="policy override is not supported"):
            reject_policy_overrides(["worktree", argument])


def test_five_percent_policy_has_consistent_fraction_and_display_definitions() -> None:
    assert Decimal("5.00") == REGRESSION_LIMIT_PERCENT
    assert Decimal("0.05") == REGRESSION_LIMIT_FRACTION
    assert PERCENT_REGRESSION_LIMIT == REGRESSION_LIMIT_FRACTION
    assert not degradation_exceeds_limit(Decimal("0.0500"))
    assert degradation_exceeds_limit(Decimal("0.0500001"))
    with pytest.raises(GovernanceError, match="finite Decimal"):
        degradation_exceeds_limit(Decimal("NaN"))


def test_production_domain_inventory_covers_the_replacement_scope() -> None:
    assert set(PRODUCTION_DOMAINS) == set(BenchmarkDomain)
    assert {domain.value for domain in PRODUCTION_DOMAINS} == {
        "canvas",
        "ecs",
        "synth",
        "python-bridge",
        "gpu",
        "spatial",
        "dsp",
        "device",
        "output",
    }
    for domain, entry in PRODUCTION_DOMAINS.items():
        assert entry.domain is domain
        assert entry.owner
        assert entry.concerns
        assert entry.capability_families
        assert entry.permitted_execution_classes


def test_execution_modes_and_local_database_policy_are_structured_and_fail_closed() -> None:
    assert set(EXECUTION_CLASS_POLICIES) == set(ExecutionClass)
    native = EXECUTION_CLASS_POLICIES[ExecutionClass.NATIVE_INTERACTIVE]
    assert "frames-presented-counter" in native.fail_closed_capabilities
    assert "headless" in native.timing_scope

    assert not MODE_POLICIES[BenchmarkMode.WORKTREE].database_writes
    assert MODE_POLICIES[BenchmarkMode.RECORD_HEAD].database_writes
    assert "exact HEAD" in MODE_POLICIES[BenchmarkMode.WORKTREE].baseline
    assert "ancestor" in MODE_POLICIES[BenchmarkMode.WORKTREE].baseline
    assert LOCAL_DATABASE_POLICY.backend == "local-filesystem"
    assert LOCAL_DATABASE_POLICY.history_directory == LOCAL_HISTORY_DIRECTORY
    assert LOCAL_DATABASE_POLICY.configurable_value == "local-history-directory-only"
