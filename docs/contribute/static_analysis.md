# Python Static Analysis

Gummy Snake type-checks all Python source under `src/` with both mypy and
BasedPyright. Ruff additionally checks the repository for lint and import
regressions. The development dependency group installs all three tools through
`uv`, so editor and command-line diagnostics use the checked configuration.

```sh
uv sync --dev
make static-analysis
# equivalent individual commands:
uv run python scripts/static_analysis_audit.py
uv run ruff check .
uv run mypy src
uv run basedpyright
```

## Coverage Ratchet

The prior configuration hid 78 Python files (about 14,130 source lines) behind
broad directory exclusions. The current configuration covers every source file
with both type checkers. Ruff permits `F822` only for the exact PBI 008 residue
file `src/gummysnake/api/three_d_api/materials_and_primitives.py`; PBI 008 owns
that copied-export cleanup and must remove the exception with it.

Do not add a directory, package, or glob exclusion for `F811`, `F821`, or
`F822`. An unavailable capability or incomplete native runtime must still fail
clearly at runtime; static-analysis settings must not introduce compatibility or
runtime fallbacks.

## Exception Manifest And No-New Gate

[`static_analysis_exceptions.toml`](static_analysis_exceptions.toml) is the
reviewed inventory for:

- mypy and BasedPyright exact-file exceptions;
- every Ruff per-file ignore; and
- every inline `type: ignore`, `pyright: ignore`, and `noqa` in `src/`, `tests/`,
  and `examples/`.

Each record names its owner, rationale, and behavior check. Temporary checker
and undefined-name exceptions also name their removal PBI. The machine-checked
[`scripts/static_analysis_audit.py`](../../scripts/static_analysis_audit.py)
compares that inventory with `pyproject.toml` and the scanned source comments.
It fails on new, stale, broad, duplicate, or unowned suppressions. Add or change
an exception only with a focused behavior test and a manifest update in the same
review.

The focused guardrail tests live in
[`tests/unit/tooling/test_static_analysis_audit.py`](../../tests/unit/tooling/test_static_analysis_audit.py).
The gate is tooling-only: it does not change sketch, renderer, ECS, synth, asset,
or runtime capability behavior.
