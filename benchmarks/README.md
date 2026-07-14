# Local-first replacement benchmarks

This package is the shared, stdlib-only foundation for the replacement benchmark
system. It intentionally does **not** import legacy benchmark scenes, examples,
or source-tree test helpers.

## Local-first policy

- A maintainer invokes performance benchmarks manually. Pull-request, merge, and
  release CI continue to automate correctness, schema, catalog, oracle, and smoke
  checks, but do not execute or gate on benchmark timing.
- Comparable history is local and ignored, keyed by the exact machine fingerprint,
  subject commit, suite, and suite version under `.scratch/benchmark/`. No remote
  branch, protected branch, or shared benchmark-data repository is authoritative.
- Comparable timing runs use isolated release builds, fixed catalog workloads,
  deterministic correctness oracles, retained raw samples, and route diagnostics.
- Percentage degradation is a fixed strict `> 5.00%` local policy. Exactly 5.00%
  passes. A zero-tolerance counter is an absolute correctness gate, not a percentage
  metric.
- Native-interactive and native-audio suites are optional, manually invoked,
  informational suites. They may be unavailable on a maintainer's machine without
  blocking benchmark, epic, or release completion, and are never replaced by a
  headless, simulated, or synthetic route.

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

`smoke` is an automated correctness path: it executes every static headless case
in the selected Canvas, ECS, or Synth catalog once through production public APIs
and writes neither records nor timing history. It excludes optional native-interactive
and native-audio cases instead of downgrading them.
### Canvas v5 catalog

`benchmarks/canvas_v1.toml` currently declares 100 exact Canvas cases: 66 bounded
headless smoke cases and 34 native-interactive cases. The catalog expands every
matrix value into its own immutable case; there are no dormant `*_matrix`
parameters or smoke-time scale overrides. Headless cases retain their declared
frame, draw, pixel, asset, and media dimensions, while native-only identities
remain optional manual cases and are skipped—not downgraded—by `smoke`.

The executable Canvas coverage includes lifecycle/first-frame/loop/redraw/idle,
30/60/120 and dynamic pacing requests, HiDPI and resize transitions, primitive and
path ladders through 100K records, global/object/`fast()` dispatch, all public
filters and blend identities, sprite/text/pixel matrices, deterministic PNG and
image operations, generated media conversion, offscreen/framebuffer churn,
deterministic public storage/compute, and OBJ/STL model import/export. Every run
uses production public APIs and validates exact callback/work counts, final
logical/physical dimensions, output sentinels, and declared public counters.

Destination-sampling blend modes are native-interactive identities because the
headless runtime correctly rejects their unavailable GPU compositing route. The
suite does not relabel runtime present completion as physical scanout. Uncapped
pacing, compositor feedback, reviewed custom fonts and non-PNG codecs, file-video
and physical capture lifecycle, native GPU compute/storage, shader churn, explicit
retained-replay/cache-memory bounds, 4K image-operation/export matrices, and direct
`SketchContext`/renderer-adapter dispatch timing remain documented runtime or
fixture blockers rather than simulated coverage.

### ECS catalog

`benchmarks/ecs_v1.toml` declares 99 executable bounded `P`/`H` cases. The Epic 290
PBI 005–009 additions include 8/64-system schedule scales, all generic physical
structural operations, 0/1K/10K event volumes with one/four readers, a 1K-row
explicit Python UDF boundary, four deterministic point distributions, every spatial
backend, HashGrid incremental updates, shared-index reuse, an auto-worker spatial
case, density-2 headless rendering, a 600-frame bounded simulation, diagnostics
snapshot/reset volume, 128-frame longevity, and stale/strict/spatial/cycle/range
failure contracts. Exact world, event, spatial, frame, and pixel digests are checked.

These identities do not imply the full PBI scales. Configurable cross-worker runs,
public change-epoch control, AABB/relation matrices, 10K/100K-frame soaks, RSS
slopes, direct-Rust harnesses, and legacy cutover remain unavailable or incomplete.
Native interactive/input/audio contention and frame-budget cases are optional manual
information and may remain unavailable. `R` and `I` requests fail closed; smoke never
substitutes `P`/`H`. See `docs/contribute/ecs_benchmark_semantics.md`.

#### Optional manual native suites

Native input/window, touch, presentation, and native-audio cases are manually invoked
when the maintainer has the required runtime and devices. They report only public,
truthful diagnostics and deterministic pre-device or callback oracles. No physical
automation driver, touch/camera/audio hardware evidence package, fixed host, or
cross-platform record is required for completion. Unavailable cases are reported as
such and do not block headless correctness, local timing history, epic completion,
or releases.

`worktree` and `record-head` use an isolated release build and refuse to substitute
source imports, a Python renderer, or synthetic measurements. The maintainer chooses
when to run them; `audit` validates local ignored history.

## Catalogs and local history

Catalogs are static TOML files with one `[suite]` table and `[[workloads]]`
tables. Workloads declare their source files, correctness oracle, execution class,
capabilities, fixed workload, sampling profile, versioned primary metric, and path
diagnostics. The parser hashes declared files into a workload definition digest;
dynamic discovery is not supported.

Records use canonical JSON with sorted keys, one newline, no binary floats, and no
non-finite values. Local ignored history is keyed by fingerprint and commit:

```text
.scratch/benchmark/history/v1/<fingerprint-id>/<subject-commit>/<suite-id>@<suite-version>.json
```

The fingerprint carries stable comparison-environment fields only. Source commit,
source snapshot, artifact hashes, and runtime build identity are provenance fields
and are explicitly excluded from the fingerprint. Local history is developer data:
it is not committed, pushed, protected, or treated as a project-wide authority.

## Operational boundary

Worker protocol v3 carries the suite identity through one registry and records two
timed blocks in each of two fresh processes under the current local profiles. Raw
blocks are retained without deletion; the decision uses the declared metric
transform and median of process medians.

Correctness is checked before timing and remains automated through catalog, oracle,
schema, and smoke tests. Comparable performance runs require release provenance,
fixed workloads, exact work accounting, raw samples, and path diagnostics. A local
regression greater than 5.00% fails; exactly 5.00% passes.

Operational procedures:

- **Invoke manually:** the maintainer runs `worktree` or `record-head`; CI does not
  execute performance timing or publish benchmark history.
- **Audit:** run `make benchmark-audit` and the relevant catalog/coverage checks
  against local ignored data.
- **Staleness:** start a new local history key when the fingerprint, catalog/suite,
  workload, metric, policy, or route meaning changes.
- **Regression triage:** retain raw blocks and diagnostics; reproduce on the exact
  fingerprint, separate correctness/capability failures from timing, and never
  bypass the 5% gate.
- **Versioning:** bump suite membership for case additions/removals, workload/case
  versions for behavior or parameters, metric versions for metric semantics, and
  policy/schema versions for statistical or encoding changes.
- **Optional native information:** interactive, touch, camera/capture, and native-
  audio suites may be run manually when available. Their absence never blocks
  completion, and their results never substitute for deterministic automated
  correctness or local exact-fingerprint comparisons.
