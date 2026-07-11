from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-stress",
        action="store_true",
        default=False,
        help="Run opt-in long-running resource lifecycle stress tests.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_stress = config.getoption("--run-stress")
    skip_stress = pytest.mark.skip(reason="need --run-stress option to run")
    for item in items:
        if "stress" in item.keywords and not run_stress:
            item.add_marker(skip_stress)
