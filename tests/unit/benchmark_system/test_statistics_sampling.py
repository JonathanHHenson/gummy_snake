from __future__ import annotations

from benchmarks.framework.statistics import (
    Decision,
    compare_samples,
    median_of_process_medians,
)
from benchmarks.schema.catalog import Direction, MetricSpec, PercentageTransform, ZeroPolicy


def latency_metric() -> MetricSpec:
    return MetricSpec(
        "elapsed",
        1,
        "ns",
        "draw",
        Direction.LOWER_IS_BETTER,
        PercentageTransform.RATIO,
        ZeroPolicy.POSITIVE_BASELINE,
        3,
    )


def test_median_and_confirmed_large_regression_are_deterministic() -> None:
    baseline = ((100, 100, 100),) * 5
    candidate = ((106, 106, 106),) * 5
    assert median_of_process_medians(baseline, 1) == 100
    first = compare_samples(latency_metric(), baseline, candidate, 1, resamples=200)
    second = compare_samples(latency_metric(), baseline, candidate, 1, resamples=200)
    assert first.decision is Decision.REGRESSION
    assert first.interval == second.interval


def test_zero_counter_is_an_absolute_gate() -> None:
    counter = MetricSpec(
        "underruns",
        1,
        "count",
        "buffer",
        Direction.LOWER_IS_BETTER,
        PercentageTransform.ABSOLUTE,
        ZeroPolicy.ZERO_TOLERANCE,
        0,
    )
    result = compare_samples(counter, ((0,), (0,)), ((0,), (1,)), 1)
    assert result.decision is Decision.ABSOLUTE_FAILURE
