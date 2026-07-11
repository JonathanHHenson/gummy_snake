from __future__ import annotations

import sys
from pathlib import Path

import pytest

from benchmarks.governance import AuthorityError, ExecutionClass
from benchmarks.worker import CapabilitySet, FreshWorker, WorkerRequest, require_capabilities


def test_capabilities_fail_closed_for_interactive() -> None:
    with pytest.raises(AuthorityError):
        require_capabilities(
            ExecutionClass.NATIVE_INTERACTIVE, CapabilitySet(runtime=True, gpu=True)
        )


def test_fresh_worker_requires_complete_single_jsonl_result(tmp_path: Path) -> None:
    worker = tmp_path / "worker.py"
    worker.write_text(
        """import json, sys
request = json.loads(sys.stdin.readline())
print(json.dumps({
 'protocol_version': 1, 'request_id': request['request_id'], 'ok': True,
 'phases': {phase: 'ok' for phase in request['phases']}, 'elapsed_ns': 10,
 'completed_work_units': request['work_units'], 'diagnostics': {}
}))
"""
    )
    request = WorkerRequest("one", ExecutionClass.HEADLESS, "fill", 1, 1, 5, 10)
    result = FreshWorker((sys.executable, str(worker))).run(request)
    assert result.elapsed_ns == 10
