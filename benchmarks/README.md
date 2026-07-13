# Governed replacement benchmarks

This package is the shared, stdlib-only foundation for the replacement benchmark
system. It intentionally does **not** import legacy benchmark scenes, examples,
or source-tree test helpers.

## Frozen authority

- The only authoritative data ref is `refs/heads/benchmark-data-v1`.
- A remote name or URL may be supplied by operations, but a caller cannot select
  another data branch, comparison threshold, fingerprint bypass, force-record,
  or arbitrary sampling override.
- Percentage degradation is a fixed strict `> 5.00%` local policy. Exactly 5.00%
  passes. A zero-tolerance counter is an absolute gate, not a percentage metric.
  Tighter statistical qualification is reserved for a reviewed future policy version.
- Missing runtime, GPU, desktop/window, display, audio, or other declared
  capability is an error. The framework does not select a fallback route.

## Commands

```sh
make benchmark-smoke
make benchmark-audit
uv run python scripts/benchmark.py catalog benchmarks/canvas_v1.toml
uv run python scripts/benchmark.py smoke benchmarks/canvas_v1.toml
uv run python scripts/benchmark.py smoke benchmarks/ecs_v1.toml
uv run python scripts/benchmark.py smoke benchmarks/synth_v1.toml
uv run python scripts/benchmark.py worktree benchmarks/canvas_v1.toml
uv run python scripts/benchmark.py record-head benchmarks/canvas_v1.toml
```

`smoke` executes every static headless case in the selected Canvas, ECS, or Synth
catalog once through production public APIs and writes neither records nor baselines.
It excludes native-interactive and native-audio cases instead of downgrading them.
`worktree` and `record-head` plan
the isolated release build and require qualified worker/runner integration. They
deliberately refuse to substitute source imports, a Python renderer, or synthetic
measurements. `audit` validates the fixed-ref immutable store.

## Catalogs and records

Catalogs are static TOML files with one `[suite]` table and `[[workloads]]`
tables. Workloads declare their source files, correctness oracle, execution
class, capabilities, sampling profile, and versioned primary metric. The parser
hashes declared files into a workload definition digest; dynamic discovery is
not supported.

Records use canonical JSON (sorted keys, one newline, no binary floats or
non-finite values) and live on the data branch as:

```text
fingerprints/v1/<first-two>/<fingerprint-id>.json
records/v1/<fingerprint-prefix>/<fingerprint-id>/<subject-prefix>/<subject-commit>/<suite-id>@<suite-version>.json
revocations/v1/<first-two>/<revocation-id>.json
```

The fingerprint carries stable comparison environment fields only. Source
commit, source snapshot, artifact hashes, and runtime build identity are
provenance fields and are explicitly excluded from the fingerprint.

## Operational boundary

Worker protocol v3 carries the suite identity through one registry and records two
timed blocks in each of two fresh processes under the current local profiles. Raw
blocks are retained without deletion; the gate uses the declared metric transform
and median of process medians.

The local Git transaction provides lock, temp-file, fsync/rename, compare-and-
swap ref update, and immutable first-writer-wins keys. Remote branch protection,
recorder authorization, and actual physical interactive/audio qualification are
operational requirements; this framework exposes errors and requirements rather
than claiming those protections or hardware timings are complete.
