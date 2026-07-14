from __future__ import annotations

from collections.abc import MutableMapping
from decimal import Decimal
from typing import cast

import pytest

from benchmarks.schema.canonical import CanonicalJsonError, canonical_json
from benchmarks.schema.records import (
    BenchmarkRecord,
    CapabilityResult,
    ComparisonEvidence,
    ComparisonFingerprint,
    CorrectnessResult,
    Invalidation,
    MetricResult,
    Provenance,
    RecordError,
    parse_benchmark_record,
)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _metric() -> MetricResult:
    return MetricResult(
        ("fill", 1, "small", _digest("a"), "elapsed", 1, 1),
        ((100, 102), (98, 100)),
        1,
        Decimal("100"),
        "ns",
        "lower-is-better",
        "ratio",
        Decimal("100"),
        True,
        "median-of-process-medians",
        3,
        "non-negative",
    )


def _record() -> BenchmarkRecord:
    metric = _metric()
    return BenchmarkRecord(
        ComparisonFingerprint(
            {
                "architecture": "AMD64",
                "hardware_architecture": "x86-64",
                "process_architecture": "x64",
                "os": {"product": "Linux", "release": "6.8", "build": "test"},
                "runtime_route": "isolated-release-wheel-canvas",
                "gpu": {"backend": "vulkan", "driver": "550.1"},
            }
        ),
        Provenance(
            "1" * 40,
            _digest("b"),
            _digest("c"),
            _digest("d"),
            _digest("e"),
            {"profile": "release", "features": ["extension-module"]},
            {"python": "3.12.0", "rustc": "1.88.0"},
        ),
        "canvas",
        1,
        _digest("f"),
        (metric,),
        {"current_load": "recorded-outside-fingerprint", "temperature_c": "observed"},
        capabilities=(CapabilityResult("gpu", True, True, "vulkan"),),
        correctness=(CorrectnessResult("pixel-checksum", True, "abc", "abc"),),
        comparisons=(
            ComparisonEvidence(
                metric.benchmark_key,
                _digest("9"),
                "pass",
                Decimal("99"),
                Decimal("100"),
                Decimal("0.0101010101"),
                Decimal("0.05"),
                "ratio",
            ),
        ),
        invalidations=(Invalidation("qualification", "simulated warning", False),),
        diagnostics={"worker": {"blocks": 4}},
    )


def test_record_round_trip_verifies_hashes_summaries_and_primary_key_path() -> None:
    record = _record()
    payload = canonical_json(record.to_dict())

    parsed = parse_benchmark_record(payload, expected_path=record.expected_path)

    assert parsed.to_dict() == record.to_dict()
    assert parsed.record_id == record.record_id
    assert parsed.primary_key == record.primary_key
    assert parsed.metrics[0].estimate == Decimal("100")
    assert parsed.capabilities[0].available
    assert parsed.correctness[0].passed
    assert parsed.comparisons[0].threshold == Decimal("0.05")
    assert parsed.run_conditions["current_load"] == "recorded-outside-fingerprint"


def test_record_parser_rejects_tampering_noncanonical_json_and_wrong_path() -> None:
    record = _record()
    tampered = record.to_dict()
    tampered["suite_id"] = "ecs"

    with pytest.raises(RecordError, match="record_id does not match"):
        parse_benchmark_record(canonical_json(tampered))
    with pytest.raises(RecordError, match="path does not match"):
        parse_benchmark_record(
            canonical_json(record.to_dict()), expected_path="records/v1/wrong.json"
        )
    with pytest.raises(CanonicalJsonError, match="not canonical"):
        parse_benchmark_record(
            canonical_json(record.to_dict()).replace(b'"capabilities"', b' "capabilities"')
        )


def test_metric_result_requires_integer_raw_samples_recomputable_summary_and_denominator() -> None:
    key = ("fill", 1, "small", _digest("a"), "elapsed", 1, 1)
    with pytest.raises(RecordError, match="integer non-negative"):
        MetricResult(
            key,
            ((True,), (100,)),
            1,
            Decimal("100"),
            "ns",
            "lower-is-better",
            "ratio",
            Decimal("100"),
        )
    with pytest.raises(RecordError, match="not recomputable"):
        MetricResult(
            key,
            ((100,), (100,)),
            1,
            Decimal("101"),
            "ns",
            "lower-is-better",
            "ratio",
            Decimal("100"),
        )
    with pytest.raises(RecordError, match="strictly positive"):
        MetricResult(
            key,
            ((100,), (100,)),
            1,
            Decimal("100"),
            "ns",
            "lower-is-better",
            "ratio",
            Decimal("0"),
        )


def test_record_payloads_are_deeply_immutable_after_identity_is_computed() -> None:
    source = {"runtime_route": "headless", "gpu": {"driver": "one"}}
    fingerprint = ComparisonFingerprint(source)
    identifier = fingerprint.id
    source_gpu = source["gpu"]
    assert isinstance(source_gpu, dict)
    source_gpu["driver"] = "two"

    stable_gpu = cast(MutableMapping[str, object], fingerprint.stable["gpu"])
    assert stable_gpu["driver"] == "one"
    assert fingerprint.id == identifier
    with pytest.raises(TypeError):
        stable_gpu["driver"] = "three"
