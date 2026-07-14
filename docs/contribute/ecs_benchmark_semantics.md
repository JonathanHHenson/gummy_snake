# ECS benchmark catalog and correctness semantics

Epic 290 ECS benchmarks are defined by `benchmarks/ecs_v1.toml` and implemented only
under `benchmarks/suites/ecs/`. They generate schemas, entities, plans, resources,
events, spatial inputs, and canvas commands in memory with the frozen seed `290001`.
They must not import examples, test fixtures, legacy benchmark scenes, or old baseline
values.

Performance runs are local-first and manually invoked by a maintainer. Comparable
history is ignored local data keyed by fingerprint and commit. Automated checks retain
catalog/schema validation, deterministic world/frame oracles, path assertions, and
headless smoke; CI does not execute ECS performance timing. Native-interactive runs
are optional manual information and may remain unavailable without blocking completion.

## Route identities

Every case declares exactly one execution layer and one path profile:

| Layer | Identity | Current availability |
| --- | --- | --- |
| `R` | Direct release `gummy_ecs` Rust harness | Unavailable; no registered direct-Rust worker route exists. |
| `P` | Public Python API → PyO3 canvas/ECS bridge → Rust ECS | Available for the cataloged direct facade cases. |
| `H` | Bounded headless sketch → public API/PyO3 → Rust ECS and Rust canvas | Available for the two integrated frame cases. |
| `I` | Native interactive SDL3 window/present route | Optional manual suite; currently unavailable. |

The declaration is fail-closed. An unavailable layer cannot fall back to `P` or `H`,
and an available layer without an implemented route is rejected. Direct smoke results
are correctness-only and do not write timing history. Nothing in this suite claims
native interactive, physical display, or direct-Rust timing when those routes are
unavailable; that absence is informational and non-blocking.

Path profiles are exact ordered identities. Every smoke result echoes
`measured_parameters`, which contains the literal dispatched scale parameters. Case IDs,
work units, and measured parameters therefore describe the same executed work; the suite
has no hidden reduced smoke scale and does not label a bounded case as a larger one.
Public ECS diagnostics additionally assert
the selected Rust core, physical-system run counts, scheduler counts, explicit Python
system/UDF boundaries, selected spatial algorithm, index rebuild/reuse behavior, and
headless canvas command path. The current `octree-incremental-96x3` case requests the
incremental policy but asserts the observed full-rebuild path and zero incremental
updates; it is not evidence that incremental updates are qualified.

## Correctness oracles

`full-world-v1` hashes canonical data obtained through public APIs:

- entity index and generation, including retired generations supplied by structural
  workloads;
- alive/dead state;
- all declared component snapshots and tag memberships;
- declared resource snapshots and ordered retained event values;
- semantic traces for cleared events, failure outcomes, and other historical facts;
- structural/field revisions and selected public diagnostics.

The runtime currently does not expose a public numeric change epoch, so the digest
records `ecs_change_epoch` as unavailable rather than inventing one. Added/Changed/
Removed epoch equivalence and configurable worker-count equivalence require additional
runtime/public API support before they can be cataloged as qualified benchmark paths.

`full-world-frame-v1` combines the world digest with a versioned exact final-frame
digest over top-left packed RGBA bytes. `PixelRule` also defines explicit bounded
per-channel tolerance (`max_channel_delta` and `max_different_channels`) for cases that
need tolerant comparison; the current integrated ECS cases use exact frame identity.

## Release provenance

Smoke dispatch is an automated correctness check, not a performance record. A
maintainer's comparable local timing run requires `isolated-release-wheel-v1`. The
recorder must, before creating workers:

1. build a release wheel from the materialized source snapshot;
2. install and import from an isolated environment rather than the source tree;
3. verify the installed native canvas artifact hash against the wheel;
4. verify canvas and ECS ABI markers;
5. require native provenance containing the source commit/digests, `release` profile,
   and `extension-module` feature; and
6. record the linked `gummy_canvas` and `gummy_ecs` crate versions.

`ReleaseProvenanceContract` mirrors the suite-relevant native checks for focused tests.
Missing or unrecorded values fail; there is no debug-build substitution.

## PBI 002–004 executable matrix

The catalog contains 99 exact workloads. The 48 PBI 002–004 matrix additions execute:

- schema registration at `1x1`, `16x4`, `64x16`, and `256x16`, with two idempotent
  validation/registration passes and exact Python/Rust schema-count assertions;
- every scalar, string/categorical, vector, and list marker in one exact storage record,
  with list lengths `0/4/32/256`, IEEE-754 Float32 readback, integer range metadata,
  vector widths, list element validation, and transactional invalid-spawn checks;
- public spawn shapes at 1K entities for `1/4/8` components, `1/4/16` fields, and
  `0/2/8` tags, plus an exact 10K single-component case;
- sparse entity IDs grown to 10K historical IDs with 100 live rows and stale-generation
  checks;
- 1K-row query selectivity at `0/1/50/100` percent, plus a Rust plan requiring a
  component while excluding another component and a tag;
- cardinalities `0/1/2/10K`, preserving the public full-scan behavior of
  `try_get_entity` instead of describing it as limit-aware optimization;
- controlled 2/3/4-query context joins with 4 origin rows, 100 target rows, one row
  per auxiliary query, exactly 400 logical contexts, and `0/1/50` percent target
  selectivity;
- `EntityView`, `ComponentView`, selected batch-field readback, and writeback over
  `1/2/8/16` scalar fields and 16-field scalar/vector/list/categorical components;
- logical plans with `10/100/1K/10K` actions, depths `1/16/128`, `1/8/64` query
  declarations, and repeated-subexpression ratios `0/50/90` percent;
- equivalent plan registration at 1 and 100 systems, 16 steady executions with exactly
  one compile, one schema-fingerprint invalidation/recompile cycle, and four fail-closed
  hostile annotation/type/schema cases.

Each matrix case stores an exact correctness digest. Plan-shape cases also return stable
explain and serialized-payload digests and exact payload action/expression counts. ECS
unit tests freeze the complete case set, matrix axes, digest set, ordered runtime paths,
work units, measured-parameter echo, and checked coverage projection.

The executable scales above are the measured scales. Larger acceptance-criteria scales
are not silently reduced:

- 100K/1M entities, million-value-per-family storage, 100K/1M churn, 1M cardinality,
  128/1024 archetypes, and million-context joins are not in bounded smoke;
- the public facade has no direct excluded-filter query iterator, so excluded component
  and tag behavior is measured through a Rust-executed logical plan;
- direct Rust (`R`) parity is blocked because no direct release `gummy_ecs` worker route
  exists;
- `exists` and grouped aggregate execution were probed, but the installed Rust runtime
  failed closed with `readonly f64 evaluator does not support` errors for both expression
  kinds. The catalog measures join contexts only and does not substitute Python execution;
- the 1,000-system public registration probe executed correctly but took about 84.6
  seconds in smoke because repeated scheduler registration/rebuild is expensive. It was
  deliberately not cataloged as a bounded smoke case; the catalog stops at 100 systems
  and does not relabel that result as 1,000 systems;
- hostile node/depth limits cannot be claimed because the public/runtime boundary does
  not currently expose declared maximums that can be asserted before allocation.

## PBI 005–009 bounded executable matrix

The 27 additional cases added for PBIs 005–009 execute their literal catalog scales:

| Area | Executed cases and exact scales | Assertions |
| --- | --- | --- |
| Scheduling | 8 systems/1 group and 64 systems/8 groups, 16 entities, 2 frames | Exact rebuilds, compiled handles, frame dispatches, physical runs, world values, and deterministic order. |
| Structural | Add/remove component, add/remove tag, and despawn at 12 of 128 rows; remove component at 128 of 128 rows | Exact entity/component/tag/generation digest, one physical run, direct structural command counts, and zero staged-command counter on the observed route. |
| Events | 0 events/1 reader, 1K/1, and 10K/4 | Exact sequence, reduction, records read, clear/queue bounds, and zero Python event mirror entries. |
| Python boundary | Explicit Python system plus runtime UDF at 1K rows | Exact writeback and declared Python system/materialization/UDF counters. The existing 128-row `udf_plan` case still requires zero runtime UDF calls. |
| Spatial distributions | Uniform/clustered/diagonal/same-cell points; all four generic algorithms at 128 rows; 0/10% movement; 1/4 sharing systems; one 512-row auto-worker case | Brute-force exact counts and order, exact selected backend, cold build/rebuild/incremental update behavior, shared-index reuse, candidate/exact counters, and reported auto worker availability. |
| Headless frames | 1K compact fills × 3 frames; density-2 256 fills × 3; 1K simulation rows × 8; 64 rows × 600 | Exact world/frame/pixel digests, logical/physical dimensions, physical runs, direct fill commands, and no entity materialization at the Python draw boundary. |
| Diagnostics/longevity/failures | 1K rows × 16 snapshots with reset every 8; 256 rows × 128 frames with 2-row churn; stale/strict/spatial/cycle/range matrix | Exact reset traces and retained plan count, bounded event queues and entity count, non-empty actionable errors, deterministic non-strict result, and no fallback route. |

These are bounded smoke and regression identities, not aliases for the larger PBI acceptance
scales. In particular:

- the public facade exposes no per-run 1/2/4/8 worker selector and no public schedule
  edge/wave/width diagnostics. The 512-row spatial case reports the runtime-selected auto
  worker count, but it is not a cross-worker scaling record;
- public facade operations do not expose an explicit next-frame change-epoch control.
  The 0/0.1/10/100% Added/Changed/Removed matrix cannot use the private `_rust.set_frame`
  mechanism from runtime tests, so it remains unclaimed;
- resource count/width matrices, event retention beyond explicit clear, storage-family UDF
  writeback, AABB datasets, joins/overlaps/origin variants, spatial structural churn, and
  handle refcount/release timing remain incomplete;
- the spatial incremental path is observed for moving HashGrid cases. Quadtree, Octree,
  and Hilbert moving cases request `incremental` but exactly assert their observed full
  rebuilds rather than relabeling them incremental;
- mixed ordered drawing remains incomplete. Native input, native interactive presentation,
  physical 60/120 Hz budgets, and canvas/ECS/synth contention are optional manual suites
  and currently unavailable. A native-interactive request fails closed with the declared
  route error and cannot downgrade to headless;
- the 128-frame longevity case is not a 10K/100K-frame soak, and no RSS/resource slope is
  inferred without a sampler.

All new correctness identities were generated by executing the exact static case and were
rechecked by full catalog smoke. They are automated correctness oracles. Local performance
history is created only by an explicit maintainer invocation and uses the fixed >5% exact-
fingerprint regression policy; no cross-platform record or hardware evidence is required.

## Metrics and current blockers

The shared recorder currently records wall-clock block samples normalized by declared
work units. Throughput is derivable. ECS diagnostics provide compiled/cache counters,
rows scanned/written, and spatial candidate/exact rows.

The catalog does **not** claim collection of CPU time, p50/p95/p99 series, peak/ending
RSS, RSS slope, bytes per row, separate storage scan/write bandwidth, archetype
transition hits/misses or bytes moved, cold-query/cache/refresh/sort phases, complete
bridge calls/objects, Python rows/tuples/scalars/temporary bytes, world clones,
reflection/serialization/PyO3/compile phase timers, expression/program bytes, spatial
key refcounts, or ECS frame/render/present phase timers. Those require shared
worker/record schema and/or runtime diagnostic changes outside the allowed benchmark
write set. The exact status and source for every required metric family is frozen in
`ECS_METRIC_REQUIREMENTS`.

`benchmarks/coverage/ecs_v1.json` is regenerated from the 99-case catalog. ECS coverage
tests compare the checked file to the exact generated projection and reject omitted,
stale, or changed entries.

## Focused commands

```sh
uv run ruff check benchmarks/suites/ecs tests/unit/benchmark_system/test_ecs*.py
uv run pytest tests/unit/benchmark_system/test_ecs_catalog.py -q
uv run pytest tests/unit/benchmark_system/test_ecs_dispatch.py -q
uv run pytest tests/unit/benchmark_system/test_ecs_coverage.py -q
uv run python scripts/benchmark.py catalog benchmarks/ecs_v1.toml
uv run python scripts/benchmark.py smoke benchmarks/ecs_v1.toml
```

Comparable release timing uses a manually invoked `worktree` or `record-head` command,
not direct suite dispatch, and writes only ignored local history keyed by fingerprint and
commit. `R` and `I` remain unavailable until dedicated routes, capability probes, and
correctness checks exist; their absence does not block completion.
