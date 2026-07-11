# Source-to-Test Impact Map

Use this map before changing a source owner. It identifies the smallest meaningful
validation route without pretending every area needs every kind of test. The
reviewable, machine-checked matrix is
[`source_test_impact_map.toml`](source_test_impact_map.toml); this guide explains
how to read and maintain it.

Run the guard after moving, renaming, adding, or retiring a source, test, example,
script, crate, or command:

```sh
uv run python scripts/impact_map_audit.py
```

The audit checks that every mapped path and command path still resolves, no named
check has an empty path group, every source owner has an explicit category decision, and
all Python source files and Cargo workspace crates have an owner. It does not run
all listed commands; use the focused command named by the affected check.

## Categories and test taxonomy

Each source area explicitly declares these categories in the TOML map:

| Category | Place code here when it is applicable | Purpose |
| --- | --- | --- |
| Unit | `tests/unit/` | Small, deterministic public API/state/wrapper behavior or a local invariant. |
| Contract | `tests/contracts/` | A backend/renderer promise that an implementation must satisfy. |
| Integration | `tests/integration/` | End-to-end sketch/runtime behavior across owned boundaries. |
| Golden | `tests/golden/` | Stable deterministic rendered output. |
| Stress | `tests/stress/` | Opt-in long-running lifecycle/resource churn. |
| Example | `examples/` | A representative bounded smoke path for user-facing behavior. |
| Documentation | `docs/` | Contributor or public guidance that must remain aligned with the owner. |
| Packaging | package manifests, assets, and `scripts/verify_distribution.py` | Distribution contents and native build inputs. |

`tests/helpers/` is reusable fake/runtime support, not a test category; keep a
helper there only when more than one test needs it. `tests/fixtures/` contains
package-resource and file inputs, not source-owned implementation behavior.

### Unit subsystem homes

Use the smallest relevant package rather than creating one directory per source
module: `api_lifecycle/` for public API, context, state, and lifecycle behavior;
`assets_media/` for assets, text, media, and pixels; `canvas_runtime/` for the
canvas/Rust adapter boundary; `ecs/`, `synth/`, and `three_d/` for those focused
subsystems; and `tooling/` for repository scripts, packaging, and topology audits.
Reusable canvas fakes belong in `tests/helpers/canvas_runtime/`; fixture files and
package resources remain under `tests/fixtures/`.

Every category is deliberately present for every area. A `N/A: ...` entry is a
reviewed statement that the category would add meaningless coverage (for example,
an enum has no independent resource stress lifecycle). Do not replace an `N/A`
with a superficial test. Conversely, replace it with a named check when a
regression demonstrates a meaningful boundary.

## Ownership and validation matrix

The TOML contains the complete per-category matrix, including each `N/A` rationale.
This compact navigation table calls out the owner and principal validation routes.
“Behavior” groups protect stable external results; “implementation” groups protect
local adapter/audit invariants and can change when internals are intentionally
refactored.

| Source owner | Boundary or role | Behavior-focused routes | Implementation-focused routes |
| --- | --- | --- | --- |
| `src/gummysnake/*.py` | package composition and compatibility shell | public API, context, drawing/golden, basic-shapes smoke | impact-map audit |
| `src/gummysnake/api/` | public composition and global-mode compatibility | public API, drawing/golden, 2D/assets smokes | — |
| `src/gummysnake/assets/` | Python wrapper over Rust asset handles | asset units, drawing/golden, lifecycle stress, asset smoke | — |
| `src/gummysnake/backend/` | canvas host/renderer composition; mandatory canvas boundary | renderer contracts, drawing/golden, bounded smoke, stress | renderer adapter characterization |
| `src/gummysnake/constants/` | enum compatibility facade | public API and basic-shapes smoke | — |
| `src/gummysnake/context_mixins/` | `SketchContext` public composition | context, contracts, drawing/golden, smokes | — |
| `src/gummysnake/core/` | shared state/value implementation | context/assets units, drawing/golden, stress | — |
| `src/gummysnake/drawing/` | 3D/protocol helpers; Rust owns native rendering | WEBGL units/integration and WEBGL smoke | — |
| `src/gummysnake/ecs/` | logical-plan facade, compatibility surface, mandatory Rust and explicit UDF boundaries | plan/bridge units, spatial stress, ECS/boids smokes | — |
| `src/gummysnake/fast_draw_runtime/` | public fast facade | context, drawing/golden, and 2D smoke | — |
| `src/gummysnake/plugins/` | lifecycle/group dispatch implementation | lifecycle/group ordering and smoke | — |
| `src/gummysnake/rust/` | mandatory ABI/capability wrapper boundary | canvas/ECS/synth bridge behavior, smokes, stress | ABI/adapter wrapper tests |
| `src/gummysnake/sketch/` | lifecycle composition and object facade | lifecycle/group ordering, contracts, drawing/golden, stress | — |
| `src/gummysnake/synth/` | Python plan/playback composition over mandatory Rust synth rendering | synth bridge behavior and synth smoke | — |
| `crates/gummy_canvas/` | mandatory canvas, SDL3, PyO3, linked ECS/synth bridge | Cargo tests, contracts, drawing/golden, stress, 2D/ECS/synth smokes | — |
| `crates/gummy_ecs/` | canonical storage/non-UDF physical execution and spatial indexes | Cargo tests, Python/Rust bridge, spatial stress, ECS smokes | — |
| `crates/gummy_synth/` | mandatory synth/sample/FX/WAV renderer | Cargo tests, Python/Rust synth bridge and synth smoke | — |
| `crates/gummy_accel/` | optional acceleration only | Cargo/wrapper tests | optional-kernel characterization |

### Composition, facades, Rust, and UDFs

Public composition roots are the package shell, `api/`, `context_mixins/`,
`backend/`, `sketch/`, and the Python ECS/synth entry points. Compatibility facades
remain testable public import/forwarding surfaces; they are not new implementation
homes. The map labels the mandatory Rust boundaries (`backend/`, `rust/`, ECS,
synth, and the three mandatory crates) so a passing fake-only unit test cannot be
mistaken for proof that the required runtime works.

`@ecs.udf` and `@ecs.system` are explicit runtime-Python boundaries. ECS logical
plans and non-UDF physical execution remain Rust-owned. Test a UDF’s Python
behavior at that boundary, but do not introduce a Python executor or a Python
component-column mirror to make a test convenient.

## Under-signaled coverage routes

The following existing checks are intentionally named rather than left as indirect
“full-suite” coverage:

- **Renderer contracts and command behavior:** `canvas_contracts`,
  `renderer_adapter`, `drawing_integration`, and `basic_shapes_golden`.
- **Lifecycle and group ordering:** `lifecycle_groups` covers draw cleanup,
  plugin ordering, and ECS schedule groups.
- **ECS Python/Rust integration:** `ecs_bridge` directly exercises plan
  compilation/execution and canvas hooks; `rust_ecs` runs the canonical Rust tests;
  `smoke_ecs` exercises representative headless sketches.
- **Synth Python/Rust integration:** `synth_bridge` covers serialized plans,
  playback bridge behavior, and packaged samples; `rust_synth` runs crate tests.
- **Audits:** `impact_map_audit` and `structure_audit` have focused unit tests and
  executable local commands.
- **Asset compilation and distribution verification:** `asset_compilation` checks
  source-defined synth/FX freshness, while `distribution` pairs sdist build input
  with the recursive Cargo/Maturin verifier tests.

## Coverage evidence and performance policy

The current package-level diagnostic evidence is the 2026-07-10 run recorded in
`[coverage_baseline]`: `412 passed`, `56 skipped`, and **77%** total Python
coverage from:

```sh
uv run pytest --cov=gummysnake --cov-report=term-missing --cov-report=xml
```

This is evidence, not a threshold or a reason to exclude meaningful code. Review a
material coverage decrease explicitly, identifying the changed behavior and whether
the new test route is proportionate. Do not weaken behavior checks or configure
exclusions merely to improve a percentage.

Performance-sensitive canvas, ECS, WEBGL, and synth changes should use a
release-built extension for local investigation, together with the relevant
functional checks, bounded smoke examples, and resource stress checks. Inspect
public diagnostics when comparing equivalent release builds. A missing mandatory
canvas, ECS, or synth capability must fail with actionable rebuild guidance—**never
substitute a Python fallback** for profiling or functional validation.

## Maintaining the map

1. Add the source glob and ownership/boundary roles when adding a top-level Python
   area or Cargo workspace crate.
2. Add a named `[checks.<name>]` table with a non-empty `paths` list and focused
   command. Label it `behavior` when it asserts a stable external result and
   `implementation` only for a deliberately local invariant.
3. Reference that check from every applicable category of every affected owner;
   write `N/A: rationale` for the remainder.
4. Run `uv run python scripts/impact_map_audit.py`, the focused test command, and
   `uv run python scripts/structure_audit.py` when paths/docs were moved.
5. For an intentional material coverage change, update the baseline evidence only
   with the command result and review rationale; do not edit it as a target.
