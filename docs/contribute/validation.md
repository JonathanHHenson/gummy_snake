# Canonical Validation Matrix

All validation commands are exposed through the root `Makefile`. Except for the
intentional `make format` target, they do not modify tracked files. Regular build
and wheel commands write only ignored artifacts below `dist/`; `make package-verify`
uses a fresh ignored `.scratch/package-verify/run.*` workspace, leaving shared
`dist/` artifacts untouched. Asset validation renders temporary outputs and
compares them to checked-in assets.

Before checks that execute drawing, ECS, synth, examples, or installed-wheel
contracts, install the required release runtime once:

```sh
uv sync --dev
make runtime-develop-release
```

The mandatory canvas extension contains the linked Rust ECS and synth runtimes.
A missing or incompatible extension is a failure with rebuild guidance, not a
reason to use a Python renderer, ECS executor, synth renderer, synthetic asset,
or reduced-quality substitute.

## Normal local and pull-request gates

| Gate | Canonical command | Local `check` | Pull request | Publish validation | Boundary proved |
| --- | --- | --- | --- | --- | --- |
| Formatting | `make format-check` | yes | yes | yes | Ruff would make no source changes. `make format` is the only mutating formatter. |
| Python quality | `make static-analysis` | yes | yes | yes | Static-analysis exception audit, Ruff lint, mypy, and reproducible basedpyright. |
| Repository/documentation paths | `make repository-audits` | yes | yes | yes | Hardened size, structure, Markdown/path, and source-to-test impact-map audits. |
| Version and packaged assets | `make version-check assets-check` | yes | yes | yes | Workspace versions agree and checked-in synth/FX assets are current. |
| Focused Python feedback | `make test-focused` | no | yes | yes | Finalized unit and contract topology from PBIs 031–033. |
| Full Python suite | `make test-full` | yes | yes | yes | Unit, contract, integration, golden, tooling, and mapped behavior tests. Benchmarks/stress remain skipped unless requested. |
| Example smoke | `make smoke`, `make smoke-extended`, `make smoke-release` | release tier | release tier | release tier | Catalog-defined bounded 2D, assets/text, ECS, WEBGL, synth, and package-asset behavior with `--no-save`/`--no-play` safeguards. |
| Rust workspace | `make rust-check` | yes | yes | yes | `cargo fmt --check`, Clippy with warnings denied, and direct crate tests for canvas, ECS, synth, and accel. |
| Source/wheel package contract | `make package-verify` | yes | Linux | native release builders | Build sdist/canvas wheel in a fresh tool-owned workspace and run the one archive verifier; no shell-glob archive selection or shared-`dist/` cleanup. |

`make check` is the supported comprehensive local gate. It requires the caller
to have installed the release canvas extension and includes all normal gates
above. It deliberately does **not** run performance or stress suites.

## Rust feature combinations

`make rust-check` always runs workspace/default-feature format and Clippy
coverage, then directly runs each member’s own test target:

| Crate | Default test route | Published-extension route |
| --- | --- | --- |
| `gummy_canvas` | `cargo test --manifest-path crates/gummy_canvas/Cargo.toml` | matching `extension-module` Clippy compile and installed-wheel smoke |
| `gummy_ecs` | `cargo test --manifest-path crates/gummy_ecs/Cargo.toml` | linked through the canvas extension wheel smoke |
| `gummy_synth` | `cargo test --manifest-path crates/gummy_synth/Cargo.toml` | linked through the canvas extension wheel smoke |
| `gummy_accel` | `cargo test --manifest-path crates/gummy_accel/Cargo.toml` | matching `extension-module` Clippy compile and optional wheel-stub verification |

Warnings are denied. PyO3 `extension-module` intentionally omits Python linker
symbols, so extension crates are tested in their default testable mode and
feature-compiled by Clippy; their release linkage is exercised by installed-wheel
smoke. The only narrow Clippy exceptions are source-local annotations where a
public Python/native bridge genuinely requires them (for example, PyO3 call
signatures with many arguments); no workflow-level Clippy suppression is
allowed.

## Distribution and native wheel smoke

`scripts/verify_distribution.py` is the only archive verifier. It discovers
exactly one archive by type inside an explicitly supplied directory and checks
both source archives and installed wheels. Pull-request Linux packaging and all
publish jobs call this same verifier rather than embedding archive-selection or
consumer scripts in YAML.

Each release wheel is built and smoked on its own native builder:

| Builder | Wheel smoke contract |
| --- | --- |
| Linux x86_64 | installed native wheel |
| macOS x86_64 | installed native wheel |
| macOS ARM64 | installed native wheel |
| Windows x64 | installed native wheel |

The isolated installed-wheel consumer verifies canvas ABI **18**, ECS ABI **4**,
mandatory health checks, a bounded headless render, Rust-owned empty ECS world
creation, non-empty Rust synth WAV rendering, bundled asset lookup, and the
clear capability error emitted when the canvas/ECS native import is deliberately
blocked. It runs outside the source checkout and rejects non-native imports.

## Explicit release-candidate gate

Performance and lifecycle stress validation remains opt-in:

```sh
make release-candidate
```

This target installs a **release** canvas extension, runs the release smoke tier,
all normal and high-count benchmark gates, and stress tests. It retains existing
benchmark floors, diagnostics, model-export memory budgets, and baseline
comparison rules; it never replaces an unavailable native capability with a
fallback. The publish workflow exposes the same gate as a manual
`release_candidate` dispatch option. Run it on the documented comparable native
machine/desktop environment before approving a release candidate—interactive
performance figures are not portable across GitHub-hosted runners.
