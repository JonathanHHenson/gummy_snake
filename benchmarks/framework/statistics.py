"""Deterministic local sampling and the current median regression policy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from ..governance import PERCENT_REGRESSION_LIMIT
from ..schema.catalog import MetricSpec, PercentageTransform, ZeroPolicy


class StatisticsError(ValueError):
    """Sampling input cannot support a valid authoritative decision."""


class Decision(StrEnum):
    PASS = "pass"
    REGRESSION = "regression"
    INCONCLUSIVE = "inconclusive"
    ABSOLUTE_FAILURE = "absolute-failure"


@dataclass(frozen=True, slots=True)
class SamplingProfile:
    id: str
    min_warmup_ns: int
    min_warmup_work: int
    processes: int
    blocks_per_process: int
    max_processes: int
    policy_version: int = 1

    def __post_init__(self) -> None:
        if (
            self.min_warmup_ns < 0
            or self.min_warmup_work < 0
            or self.processes < 2
            or self.blocks_per_process < 1
            or self.max_processes < self.processes
            or self.policy_version < 1
        ):
            raise StatisticsError("invalid sampling profile")


PROFILES: dict[str, SamplingProfile] = {
    "micro": SamplingProfile("micro", 1_000_000_000, 10_000, 2, 2, 2),
    "bulk-headless": SamplingProfile("bulk-headless", 2_000_000_000, 1_000, 2, 2, 2),
    "frame-headless": SamplingProfile("frame-headless", 2_000_000_000, 120, 2, 2, 2),
    "frame-interactive": SamplingProfile("frame-interactive", 3_000_000_000, 120, 2, 2, 2),
    "simulated-realtime": SamplingProfile("simulated-realtime", 3_000_000_000, 120, 2, 2, 2),
    "native-audio": SamplingProfile("native-audio", 3_000_000_000, 120, 2, 2, 2),
}


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    decision: Decision
    baseline_estimate: Decimal
    candidate_estimate: Decimal
    change: Decimal | None
    interval: None
    reason: str


def _median(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise StatisticsError("median requires samples")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)


def normalized_process_medians(
    blocks_ns: Sequence[Sequence[int]], work_per_block: int
) -> tuple[Decimal, ...]:
    if work_per_block <= 0 or not blocks_ns or any(not blocks for blocks in blocks_ns):
        raise StatisticsError("samples require non-empty process blocks and positive declared work")
    medians: list[Decimal] = []
    for process in blocks_ns:
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in process
        ):
            raise StatisticsError("raw samples must be non-negative integer nanoseconds")
        medians.append(_median([Decimal(value) / Decimal(work_per_block) for value in process]))
    return tuple(medians)


def median_of_process_medians(blocks_ns: Sequence[Sequence[int]], work_per_block: int) -> Decimal:
    """The authoritative point estimate; blocks are never flattened across workers."""

    return _median(normalized_process_medians(blocks_ns, work_per_block))


def compare_samples(
    metric: MetricSpec,
    baseline_blocks_ns: Sequence[Sequence[int]],
    candidate_blocks_ns: Sequence[Sequence[int]],
    work_per_block: int,
    *,
    family_size: int = 1,
    resamples: int = 2_000,
    at_max_stage: bool = True,
    seed: int = 270_005,
) -> ComparisonResult:
    """Apply absolute zero gates or the configured strict regression threshold."""

    baseline = median_of_process_medians(baseline_blocks_ns, work_per_block)
    candidate = median_of_process_medians(candidate_blocks_ns, work_per_block)
    if metric.transform is PercentageTransform.ABSOLUTE:
        if metric.absolute_gate_failed(candidate):
            return ComparisonResult(
                Decision.ABSOLUTE_FAILURE,
                baseline,
                candidate,
                None,
                None,
                "candidate violated the metric's absolute correctness gate",
            )
        return ComparisonResult(
            Decision.PASS,
            baseline,
            candidate,
            None,
            None,
            "candidate remained within the metric's absolute correctness gate",
        )
    if metric.zero_policy not in (ZeroPolicy.POSITIVE_BASELINE, ZeroPolicy.EXPLICIT_TRANSFORM):
        raise StatisticsError("unsupported metric zero policy for authoritative percentage gate")
    if metric.requires_positive_baseline and baseline <= 0:
        raise StatisticsError("percentage comparison requires a strictly positive denominator")
    change = metric.percentage_change(baseline, candidate)
    _ = family_size, resamples, at_max_stage, seed
    if change > PERCENT_REGRESSION_LIMIT:
        return ComparisonResult(
            Decision.REGRESSION,
            baseline,
            candidate,
            change,
            None,
            "median-of-process-medians exceeds 5.00% degradation",
        )
    return ComparisonResult(
        Decision.PASS,
        baseline,
        candidate,
        change,
        None,
        "median-of-process-medians is at or below 5.00% degradation",
    )
