"""Deterministic hierarchical sampling and the current regression decision policy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from random import Random

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
    bootstrap_resamples: int = 2_000
    confidence: Decimal = Decimal("0.99")

    def __post_init__(self) -> None:
        if (
            self.min_warmup_ns < 0
            or self.min_warmup_work < 0
            or self.processes < 2
            or self.blocks_per_process < 1
            or self.max_processes < self.processes
            or self.bootstrap_resamples < 100
            or not Decimal(0) < self.confidence < Decimal(1)
        ):
            raise StatisticsError("invalid sampling profile")


PROFILES: dict[str, SamplingProfile] = {
    "micro": SamplingProfile("micro", 1_000_000_000, 10_000, 9, 5, 27),
    "bulk-headless": SamplingProfile("bulk-headless", 2_000_000_000, 1_000, 9, 5, 27),
    "frame-headless": SamplingProfile("frame-headless", 2_000_000_000, 120, 9, 5, 27),
    "frame-interactive": SamplingProfile("frame-interactive", 3_000_000_000, 120, 11, 5, 33),
    "simulated-realtime": SamplingProfile("simulated-realtime", 3_000_000_000, 120, 11, 5, 33),
    "native-audio": SamplingProfile("native-audio", 3_000_000_000, 120, 11, 5, 33),
}


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    lower: Decimal
    upper: Decimal
    confidence: Decimal
    family_size: int
    seed: int


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    decision: Decision
    baseline_estimate: Decimal
    candidate_estimate: Decimal
    change: Decimal | None
    interval: BootstrapInterval | None
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


def _resampled_estimate(blocks: Sequence[Sequence[int]], work: int, random: Random) -> Decimal:
    process_medians: list[Decimal] = []
    for _ in range(len(blocks)):
        process = blocks[random.randrange(len(blocks))]
        resampled = [
            Decimal(process[random.randrange(len(process))]) / Decimal(work) for _ in process
        ]
        process_medians.append(_median(resampled))
    return _median(process_medians)


def hierarchical_bootstrap(
    metric: MetricSpec,
    baseline_blocks_ns: Sequence[Sequence[int]],
    candidate_blocks_ns: Sequence[Sequence[int]],
    work_per_block: int,
    *,
    resamples: int = 2_000,
    family_size: int = 1,
    seed: int = 270_005,
) -> BootstrapInterval:
    """Jointly resample process clusters and blocks with a reproducible stdlib PRNG."""

    if metric.transform is not PercentageTransform.RATIO:
        raise StatisticsError("hierarchical percentage bootstrap is only valid for ratio metrics")
    if family_size < 1 or resamples < 100:
        raise StatisticsError("invalid bootstrap family size or resample count")
    # Validate denominators before random work so zero policies never become an accident.
    baseline_estimate = median_of_process_medians(baseline_blocks_ns, work_per_block)
    if baseline_estimate <= 0:
        raise StatisticsError("ratio comparison requires a strictly positive baseline estimate")
    random = Random(seed)
    changes: list[Decimal] = []
    for _ in range(resamples):
        baseline = _resampled_estimate(baseline_blocks_ns, work_per_block, random)
        candidate = _resampled_estimate(candidate_blocks_ns, work_per_block, random)
        if baseline <= 0:
            raise StatisticsError("bootstrap produced non-positive ratio denominator")
        changes.append(metric.percentage_change(baseline, candidate))
    changes.sort()
    # Bonferroni is the committed family-wise method.  Two-sided interval uses alpha/2.
    alpha = (Decimal(1) - Decimal("0.99")) / Decimal(family_size)
    tail = alpha / Decimal(2)
    lower_index = max(0, int(tail * len(changes)))
    upper_index = min(len(changes) - 1, int((Decimal(1) - tail) * len(changes)) - 1)
    return BootstrapInterval(
        changes[lower_index], changes[upper_index], Decimal("0.99"), family_size, seed
    )


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
    if metric.zero_policy is ZeroPolicy.ZERO_TOLERANCE:
        if candidate != 0:
            return ComparisonResult(
                Decision.ABSOLUTE_FAILURE,
                baseline,
                candidate,
                None,
                None,
                "zero-tolerance metric observed a non-zero candidate value",
            )
        return ComparisonResult(
            Decision.PASS, baseline, candidate, None, None, "zero-tolerance metric remained zero"
        )
    if metric.zero_policy is not ZeroPolicy.POSITIVE_BASELINE:
        raise StatisticsError("unsupported metric zero policy for authoritative percentage gate")
    interval = hierarchical_bootstrap(
        metric,
        baseline_blocks_ns,
        candidate_blocks_ns,
        work_per_block,
        resamples=resamples,
        family_size=family_size,
        seed=seed,
    )
    change = metric.percentage_change(baseline, candidate)
    if interval.lower > PERCENT_REGRESSION_LIMIT:
        return ComparisonResult(
            Decision.REGRESSION,
            baseline,
            candidate,
            change,
            interval,
            "99% interval confirms >5.00% degradation",
        )
    if interval.upper <= PERCENT_REGRESSION_LIMIT:
        return ComparisonResult(
            Decision.PASS,
            baseline,
            candidate,
            change,
            interval,
            "99% interval is at or below 5.00%",
        )
    state = Decision.INCONCLUSIVE if at_max_stage else Decision.INCONCLUSIVE
    reason = (
        "maximum sampling stage unresolved"
        if at_max_stage
        else "additional sampling stage required"
    )
    return ComparisonResult(state, baseline, candidate, change, interval, reason)


def split_half_stable(
    metric: MetricSpec,
    blocks_ns: Sequence[Sequence[int]],
    work_per_block: int,
    *,
    family_size: int = 1,
) -> ComparisonResult:
    """A/A stability gate required before an unseen fingerprint can seed authority."""

    if len(blocks_ns) < 4:
        raise StatisticsError("split-half stability requires at least four worker processes")
    midpoint = len(blocks_ns) // 2
    return compare_samples(
        metric,
        blocks_ns[:midpoint],
        blocks_ns[midpoint:],
        work_per_block,
        family_size=family_size,
    )
