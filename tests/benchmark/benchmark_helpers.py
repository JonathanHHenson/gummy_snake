from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def json_payload_from_process(
    result: subprocess.CompletedProcess[str],
    failure_label: str,
) -> dict[str, Any]:
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise AssertionError(f"{failure_label} failed\n{detail}")
    stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not stdout_lines:
        detail = result.stderr.strip()
        raise AssertionError(f"{failure_label} produced no JSON payload\n{detail}")
    try:
        payload = json.loads(stdout_lines[-1])
    except json.JSONDecodeError as exc:
        detail = (result.stdout + result.stderr).strip()
        raise AssertionError(f"{failure_label} produced invalid JSON\n{detail}") from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"{failure_label} JSON payload must be an object: {payload!r}")
    return payload


def run_json_subprocess(args: Sequence[str], failure_label: str) -> dict[str, Any]:
    result = subprocess.run(
        list(args),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return json_payload_from_process(result, failure_label)
