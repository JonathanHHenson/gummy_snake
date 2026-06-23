from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-benchmarks",
        action="store_true",
        default=False,
        help="Run opt-in runtime benchmark tests.",
    )
    parser.addoption(
        "--run-high-count-benchmarks",
        action="store_true",
        default=False,
        help="Run opt-in high-count benchmark gates such as 50k and 100k primitive scenes.",
    )
    parser.addoption(
        "--run-stress",
        action="store_true",
        default=False,
        help="Run opt-in long-running resource lifecycle stress tests.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_benchmarks = config.getoption("--run-benchmarks")
    run_high_count_benchmarks = config.getoption("--run-high-count-benchmarks")
    run_stress = config.getoption("--run-stress")
    skip_benchmark = pytest.mark.skip(reason="need --run-benchmarks option to run")
    skip_high_count_benchmark = pytest.mark.skip(
        reason="need --run-high-count-benchmarks option to run"
    )
    skip_stress = pytest.mark.skip(reason="need --run-stress option to run")
    for item in items:
        if "benchmark" in item.keywords and not run_benchmarks:
            item.add_marker(skip_benchmark)
        if "high_count_benchmark" in item.keywords and not run_high_count_benchmarks:
            item.add_marker(skip_high_count_benchmark)
        if "stress" in item.keywords and not run_stress:
            item.add_marker(skip_stress)
