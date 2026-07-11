# Runtime Contracts

This document is the contributor baseline for behavior-preserving runtime work. It
complements the public API contract tests: it freezes the mandatory Rust runtime
boundary, not a private Python or Rust implementation layout.

## ABI and capability contract

| Surface | Current contract | Validation owner |
| --- | --- | --- |
| Canvas ABI | version `18`, exposed by `canvas_abi_version()` and the legacy `CANVAS_ABI_VERSION` module attribute | `gummysnake.rust.canvas.require_canvas_runtime()` |
| ECS ABI | version `4`, exposed by `ecs_abi_version()` through `_canvas` | `gummysnake.rust.ecs.require_ecs_runtime()` |
| Canvas/ECS health | a callable health probe must return a non-empty string other than `"unavailable"` | the same pre-construction validators |
| Runtime shape | canvas asset/state classes and ECS world/registry classes must be present and constructible | the same pre-construction validators |

Markers must be native integer values. Strings, floats, booleans, missing probes,
probe errors, and mismatches are capability failures, not coercion opportunities.
Every failure raises `BackendCapabilityError` with the release rebuild command:

```sh
uvx maturin develop --release --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
```

Validation happens before `CanvasBackend` creates a renderer and before the Python
ECS facade creates an `EcsWorld` or spatial registry.

## Ownership and no-fallback contract

| Behavior | Mandatory Rust owner | Python role | Failure rule |
| --- | --- | --- | --- |
| Headless and interactive canvas, state, pixels, text, and assets | `gummy_canvas` | lifecycle, public validation, adapters | missing runtime raises; no Python/Pillow/Pyglet renderer |
| Non-UDF ECS storage and plans | `gummy_ecs`, linked by `gummy_canvas` | schema/plan declaration and views | unsupported physical work raises; only explicit UDF/system bodies execute Python |
| Synth, sample, FX, WAV, and playback-plan rendering | `gummy_synth`, linked by `gummy_canvas` | plan construction and playback controls | missing or malformed bridge raises; no Python synth/sample/FX renderer |

Headless mode is bounded/offscreen canvas behavior, never a different Python
renderer. Runtime performance diagnostics must continue to distinguish an explicit
UDF call from a prohibited `ecs_python_fallback_system_runs` execution.

## Lifecycle, ordering, and HiDPI contract

A normal sketch `draw()` is registered in the built-in ECS `draw` group. Group
execution is wrapped by generated plugin hooks: `before_<group>` and
`after_<group>`, including `before_draw` and `after_draw`. A completed frame
updates timing/context state, executes ordered groups, ends rendering, ends context
state, consumes a pending redraw, and then advances `frame_count`. Failure cleanup
runs without incorrectly advancing completed-frame state.

Canvas dimensions remain logical at the public API while backing buffers and pixel
arrays are physical. SDL3 pointer, wheel, and touch payloads carrying
`coordinates = "logical"` are never divided by density again. One-character native
key names are normalized to lowercase before reaching Python.

Primitive, image, text, clip, and effect commands remain visibly ordered by call
order despite internal batches and render-pass segments. Shape/clip capture is
finalized directly from Rust-owned buffers. Dirty `PixelBuffer` uploads preserve
physical row alignment and avoid unnecessary full-buffer copies. Retained model
handles use the Rust model/GPU resource path when supported; unsupported paths must
fail clearly rather than introduce a Python renderer fallback.

## Rust source compatibility contract

`gummy_ecs` root re-exports and public DTO construction used by `gummy_canvas` are
source-compatibility surfaces. The compile fixture at
`tests/fixtures/rust/downstream_runtime_api/` is the external-consumer check for
these imports, ABI/version constants, plan DTOs, execution reports, scheduler, and
spatial construction paths.

`gummy_canvas` intentionally has no supported downstream Rust API: its supported
surface is the Python `_canvas` extension validated above.

`gummy_synth` is a PyO3-free typed Rust library. It exposes `SynthError`,
`SynthResult`, typed event values, `render_serialized_plan_wav_bytes`,
`SynthPlaybackPlan::from_serialized_plan`, and
`SynthPlaybackPlan::render_window_i16`. Its public `codec` module owns the
bounds-checked RIFF/WAV chunk scanner and optional metadata used by both synth
sample decoding and `gummy_canvas`; it does not choose a supported audio format
or construct Python errors. Synth samples retain their mono/stereo 8-, 16-, and
32-bit PCM WAV plus FLAC policy, while canvas duration probing and SDL playback
retain their respective metadata and uncompressed 16-bit PCM policies.
`gummy_canvas/src/bindings/synth.rs` owns all Python dict/list parsing,
registration of the existing `_canvas` synth functions, and conversion of typed
synth failures back to the established Python `ValueError` messages.
`SynthPlaybackPlan::duration_seconds` remains an ordinary domain API.

### WAV caller-policy matrix

The shared parser is intentionally structural. These callers retain their prior
format decisions and public failure behavior:

| Consumer | Accepted format policy | Container/error policy |
| --- | --- | --- |
| Synth sample decoder | Mono or stereo 8-, 16-, or 32-bit PCM-width WAV data; FLAC stays on its existing decoder path. The WAV audio-format tag is retained as metadata but is not a new synth decoder filter. | Unknown RIFF chunks and odd-byte padding are ignored; malformed chunks, missing required chunks, and unsupported width/channel combinations remain `SynthError` failures. A final incomplete stereo frame retains the prior truncation behavior. |
| `CanvasSound` duration probe | Any WAV metadata that can determine frame bytes; it does not impose the SDL playback format restriction. | Non-WAV and incomplete metadata produce `None`; malformed chunk lengths and `fmt ` chunks retain their `ValueError` messages. |
| SDL synth WAV playback | Exactly uncompressed 16-bit PCM with non-zero channel count/sample rate and 16-bit-aligned data. | The canvas adapter maps typed policy failures back to the existing `ValueError` messages before SDL stream setup. |

## Diagnostics and performance baseline

Public renderer counters are exposed through `renderer_performance_counters()` and
public ECS counters through `ecs_diagnostics()`. Keep their names and meanings in
[Runtime diagnostics](runtime_diagnostics.md) stable. Hot Rust ECS claims require
`ecs_physical_system_runs > 0`, `ecs_udf_calls == 0`, and no physical-plan or
physical-execution errors.

Use a release-built canvas extension for performance comparison. Interactive canvas
and WEBGL scenarios require a 240 FPS mean floor; recovered scenes retain their
documented margin objectives. Model export retains its streaming memory budget, not
an FPS target. Existing benchmark TOML files are machine/build observations, not
portable CI timing claims: compare only matching machine, OS, interpreter, revision,
and release-build fingerprints.

Offline synth performance is deterministic serialized-plan rendering, including
packaged samples and FX. Record WAV format, frame count, non-silence, and repeated
render byte equality; report local render time but do not make native playback a
wall-clock gate. Capture a new benchmark baseline only from a measured release run;
do not promote historical debug or compatibility-executor measurements.

## Required contract checks

```sh
uv run pytest tests/unit/test_rust_canvas.py tests/unit/test_ecs_bridge.py \
  tests/unit/test_lifecycle.py tests/unit/test_ecs_schedule.py \
  tests/unit/test_ecs_core.py tests/unit/test_ecs_plans.py \
  tests/unit/test_pixels_export_blend.py tests/unit/test_synth_tracks_plan.py -q
cargo check --manifest-path tests/fixtures/rust/downstream_runtime_api/Cargo.toml
cargo test --workspace
```

For release performance work, build with the release Maturin command above, then
run the relevant opt-in canvas, WEBGL, ECS, model-export, and offline-synth
benchmarks. Do not treat a debug extension or native audio playback timing as a
release performance result.
