# Synth benchmark semantics

This document defines correctness semantics for the replacement synth benchmark
catalogue (`benchmarks/synth_v1.toml`). It prevents a timing baseline from silently
blessing a known rendering or playback defect. Performance runs are manually invoked
and stored as ignored local history keyed by fingerprint and commit; automated checks
retain deterministic fixtures, signal/PCM oracles, path checks, schemas, and headless
smoke. Native-audio runs are optional manual information and may be unavailable without
blocking completion.

## Ownership and measured boundaries

```mermaid
flowchart LR
    Python[Python composition and lazy values]
    Expand[Physical-plan expansion and validation]
    Serialize[Versioned GSS serialization]
    Bridge[Mandatory canvas PyO3 bridge]
    Compile[Rust compiled synth program]
    DSP[Voices samples FX and output DSP]
    Sink[WAV memory file or SDL queue sink]
    Device[Native SDL audio device]

    Python --> Expand --> Serialize --> Bridge --> Compile --> DSP --> Sink
    Sink --> Device
```

Python owns logical composition, source synth/FX expansion, public argument
validation, and serialization of a bounded physical plan. `gummy_canvas` owns
the PyO3 boundary and maps failures into the established package exception
surface. `gummy_synth` owns physical-plan decode/compile, source/sample DSP,
FX, normalisation, PCM conversion, WAV output, and native audio data supplied to
SDL. Python never schedules individual audio events on a device thread.

Benchmark cases must record the phase they measure. Composition, expansion,
serialization, bridge/compile, DSP, output, queueing, and presentation/device
phases are different measurements and must not be combined under an ambiguous
"render time" label.

## Deterministic plan and control contract

A physical plan is identified by its serialized semantic content, track seed,
and stable plan-local event identity. Equal frame events are ordered by rounded
frame, declared event order, then node identifier. Same-frame controls retain
their declared input order; later controls for the same target/field win.

A target control begins at its rounded target frame. A `*_slide` changes the
value from the value effective at that target frame and uses the documented
sample-rate timeline; it does not begin one frame early. A running source or
shared FX processor must accept controls while its input is silent and while its
tail is draining. A benchmark that only checks controls at event creation does
not qualify the running-control contract.

Event/instance/voice stochastic identity is derived from the track seed and
stable plan-local identifiers. It must not depend on process-global allocation,
previous track builds, worker count, or hash-map iteration order.

## Composition, template, and schedule matrices

Epic 310 composition cases are executable public-API workloads; scale labels are
not inferred from smaller runs:

- flat declarations run at exactly 1, 64, 1,024, 16,384, and 65,536 events;
- compact loop/thread/track-call plans and directly expanded plans are compared at
  every nesting depth from 1 through 8;
- lazy expression graphs cover arithmetic, seeded random values, choice/ring,
  tick/look, music values, conditions, lazy sleep and sample duration, nested
  containers, and track-call binding reuse at geometric sizes through 4,096;
- source synth/FX templates cover override remapping, two source outputs, and an
  actively controlled FX handle; compiled `beep`, `prophet`, `lpf`, and `reverb`
  assets are loaded twice with exact digest checks;
- dense, sparse, simultaneous, open, and finite schedules run at 1, 64, and 1,024
  events, while control schedules run at exactly 0, 64, and 16,384 controls.

Each scale point reports declaration, physical expansion/sort, normalization, and
serialization measurements where the public API exposes those boundaries. The
production sorter is part of `physical_plan()` and has no separate public timer,
so `production_sort_ns` is explicitly unavailable rather than estimated. Object
memory is reported only as labelled shallow `sys.getsizeof()` bytes; phase
allocation metrics are net `sys.getallocatedblocks()` boundary deltas, not exact
allocation counts.

Template “cold/warm” data means first load in the benchmark process followed by
an immediate reload. The suite does not flush the operating-system page cache and
therefore records this limitation in every asset result. Public template loaders
expose no cache byte/hit/miss counters, so those metrics remain unavailable.

Fresh-process composition launches four bounded Python children: same-seed twice,
same-seed after an unrelated track, and a changed seed. Equal seeds must preserve
the normalized plan digest regardless of prior unrelated composition; the changed
seed must change the stochastic identity. A 65-level nested value is also required
to fail at the documented value-depth limit.

The benchmark framework currently has no smoke parameter override. Consequently,
`benchmarks smoke benchmarks/synth_v1.toml` runs these declared scales exactly.
The suite does not label a reduced smoke execution as 65K work.

## Voice, envelope, filter, and automation matrices

The catalog supplements the original focused voice cases with two explicit
production-path matrices:

- `voice-families-rates-polyphony-matrix` renders all ten supported primitive
  oscillator/noise/FM families at 44.1, 48, and 96 kHz and at 1, 4, and 12 notes.
  Its 90 work units are actual family × rate × polyphony cells. Every cell is
  rendered twice through public `Track`/`PhysicalPlan` APIs and requires exact
  same-build WAV bytes plus finite bounded signal statistics.
- `layers-envelopes-filters-automation-matrix` executes 90 actual render cells:
  2/4/7/16 layers at 1/4-note polyphony; envelope curves -4/-1/1/3/4/7 with both
  zero-edge and nonzero stage profiles; LPF/RLPF/HPF/RHPF/wobble/NRLPF paths; and
  0/1/8/64 controls for note, amp, pan, pulse width, cutoff, and resonance with
  slides. It checks declared control counts, same-frame declaration order, exact
  repeat PCM, envelope shape where the window oracle is applicable, and signal
  summaries.

Polyphony elapsed slope is derived only from measured endpoint totals. Public
Synth diagnostics currently expose neither per-voice temporary bytes nor phase,
filter coefficient-update, or automation-cursor lookup counters; those fields
are explicitly unavailable rather than inferred.

## Sample decode, resample, and cache matrices

`pcm-flac-decode-metadata-matrix` performs 54 real metadata decode calls: cold and
immediate warm calls for the 24 generated mono/stereo 8/16/32-bit PCM cells at
8/16/44.1/48 kHz, plus the three pinned package FLAC assets. Fixture bytes,
channels, widths, frames, rates, durations, and hashes are exact, and public
`gil_released_decode_calls` must account for the calls.

`sample-resample-slice-playback-rate-matrix` renders 30 source/target/playback
cells through public sample events: 44.1/48 kHz sources, 44.1/48/96 kHz outputs,
and rates -1, 0.125, 0.5, 1, and 8 over the exact `[0.125, 0.875]` slice. Every
cell requires repeat PCM, finite non-silent output, and an unchanged source-file
digest. Reverse playback is therefore real negative-rate DSP, not reversed
post-render bytes.

The suite also retains the generated/package cold/warm identity case. The public
runtime does not expose sample-cache hits, misses, evictions, lock time,
resampled bytes, or a configured cache budget, so cache pressure, stale-file
invalidation, and byte/RSS recovery remain incomplete. No cache metric is
manufactured from call timing.

## Serialization and bridge matrices

Serialization shape profiles sweep events (1/64/1,024/16,384), controls
(0/64/16,384), value depths (1/8/32), oscillator layers (1/4/16), FX depths
(0/4/16/64), and repeated explicit sample paths (1/8/64). No audio render occurs
in this matrix. Every profile independently measures:

1. `PhysicalPlan.to_dict()` and value normalization;
2. canonical JSON encoding;
3. zlib compression;
4. zlib decompression;
5. JSON parsing;
6. Python typed conversion and validation;
7. binary container construction;
8. full Python container round trip;
9. aggregate `CanvasSynthProgram.from_serialized()` Rust compile preparation.

The aggregate Rust phase includes decompression, parse, typed conversion,
validation, control indexing, and renderer preparation. The current public runtime
does not split those internal phase timers, expose Rust allocator counters, or
expose bridge-copy counters. Those values are emitted with `available=false` and
an actionable reason. Exact JSON/compressed/container/input byte lengths and
public GIL-release compile counters remain available. Direct and serialized
compile/render routes additionally report separate elapsed phases and require
byte-exact accepted PCM parity.

The hostile matrix performs 24 bounded expected failures spanning short/corrupt
headers, unsupported compression, corrupt/truncated/trailing zlib data, invalid
JSON and schemas, NaN/infinity, zero/unsupported rates, negative/huge times,
output-frame limits, unsupported values, non-string mapping keys, excessive value
depth, declared decompressed-size limits, malformed RIFF/sample resources, and
unknown primitive/FX/chain operations. It never invokes an alternate parser,
decoder, or renderer after failure.

## Output and partition policy

There are three comparison levels:

| Policy | Required use | Comparison |
| --- | --- | --- |
| Exact structural | plan expansion and serialization | Exact canonical digest and event/control order |
| Exact PCM | same target, build, source plan, and worker configuration | Byte-identical interleaved PCM/WAV |
| Signal tolerance | different supported native platforms or audio backends | Same frame count, finite samples, channel/routing invariants, and reviewed numerical tolerance |

A true block-partition check renders the same compiled program through different
block partition sequences using persistent source, FX, limiter, and normaliser
state. Slicing an already fully rendered buffer is **not** a block-partition
benchmark and must not be labelled as one.

The current public `Track.render()` and uncached `Track.save()` routes both use the
canonical Rust `StatefulBlockRenderer`. Memory output feeds its explicit memory
WAV sink; uncached file output feeds its incremental seekable WAV sink without a
duration-sized intermediate DSP buffer. The
`stateful-block-memory-file-parity` case creates independent tracks so `save()`
cannot reuse the Python render cache, then requires byte-exact sink parity. The
1/10/60-second output case does the same and truthfully counts 142 rendered
audio-seconds (71 seconds through each sink). These are true block-render and
streaming-file routes.

Python does not currently expose block-size selection, renderer stepping,
backpressure injection, or per-session `BlockRenderDiagnostics`. Arbitrary
partition equivalence, queue `WouldBlock`, normaliser partition equivalence, and
block workspace high-water records therefore remain unavailable. The older
`simulated-realtime-pcm-block-sink` case is explicitly a deterministic
**post-render PCM partition adapter**; it tests simulated queue accounting but is
not evidence for stateful DSP partition equivalence.

The causal normaliser contract is versioned separately in
[`synth_normaliser_migration.md`](synth_normaliser_migration.md): it uses fixed
lookahead, linked stereo gain, sample-rate-scaled attack/release, deterministic
finite flush, and no whole-program future peak scan. The historical
whole-buffer global-peak normaliser is non-authoritative and is never a
correctness oracle for a new block-engine baseline.

Finite programs finish only after source and processor tails plus normaliser
latency have drained. Open/rolling programs stay bounded and do not perform a
finite flush until explicitly closed.

## Suite identities and capability rules

- **Offline/headless** cases use the mandatory Canvas/Synth runtime with no
  device requirement. They measure compile, DSP, output, and deterministic
  simulated sink behavior.
- **Simulated realtime** cases use a bounded queue/backpressure simulation with
  the same native DSP engine. They measure block deadline, prefill, queue
  watermark, underrun, stop, and cleanup behavior; they are not native-device
  evidence.
- **Native device** cases are optional manual informational runs. When invoked they
  require the declared SDL device and exact device/system/build fingerprint. Device
  absence, permission failure, or an unsupported format reports the suite unavailable
  without blocking completion, and never selects the simulated or offline route as a
  substitute.

All comparable local timing records must include release provenance for `gummy_synth`
and the Canvas extension. A debug extension or non-release Rust library is not a
comparable performance baseline.

## Self-contained fixtures and adapters

`benchmarks/suites/synth/fixtures.py` owns the benchmark corpus. The default
signal manifest pins reviewed WAV hashes for mono/stereo impulses, silence,
sine, dual-tone, chirp, seeded noise, asymmetric stereo, transients, and an
envelope/control signal. The PCM matrix is generated without a codec dependency
and covers mono and stereo, 8/16/32-bit integer PCM, and 8,000/16,000/44,100/
48,000 Hz. Temporary decoder files are removed at the fixture boundary.

Real FLAC coverage reuses three package-owned CC0 Sonic Pi samples rather than
checking in duplicate audio. Their relative paths, byte lengths, SHA-256 hashes,
roles, and native-decoder durations are pinned. `bd_pure.flac` is the minimal
reviewed FLAC fixture; `drum_cymbal_closed.flac` and `loop_amen.flac` provide
transient and loop/cache scales. MP3 is a separate FFmpeg capability result. A
missing `ffmpeg` reports unavailable and never selects another encoder.

All adapters use `prepare`, `warm`, `timed`, `synchronize`, `validate`, and
`teardown`. Their identities distinguish cold direct/serialized compile routes
from warm compiled-program and file-sink routes. The simulated realtime adapter
partitions already rendered exact production PCM using a deterministic virtual
clock; it reports block-frame and measured adapter-operation distributions but
is neither stateful DSP-partition nor device evidence.

The optional SDL adapter is intentionally fail-closed in the current runtime.
SDL playback can open and stop, but the public bridge does not expose negotiated
format/rate/channels, queue watermarks, underruns, or a stop/reopen result. The
adapter therefore reports unavailable before opening a device.
`stateful-partition-rolling-native-route-guards` exercises this pre-open guard and
confirms that no device was opened. It also records that arbitrary block/session
diagnostics and a deterministic headless rolling sink are unavailable. No hardware
evidence, microphone input, serial identifier, or private device identifier is
required or collected, and unavailability does not block completion.

## Metrics

Every adapter records monotonic phase timings and p50/p95/p99/max distributions.
Block adapters additionally record the distribution of measured per-block
adapter operations. Exact output byte counts are reported when the route exposes
bytes or a file payload. `sys.getallocatedblocks()` deltas and process peak-RSS
deltas from `resource.getrusage()` are reported with their source when available;
they are not mislabeled as exact allocation counts or current RSS. Unsupported
platform metrics are represented by `{available = false, value = null, reason =
...}`.

Cache hit/miss/byte metrics use the same availability schema. The current sample
cache exposes no public counters, so the benchmark records explicit cold/warm
canonical-path identities and marks cache counters unavailable instead of
inventing values. The same rule applies to Rust allocation counts, bridge copy
counts, exact GIL-held intervals, and split Rust deserialize/validate/index/prepare
timers: only exact input/output/intermediate byte lengths, net Python allocation
block deltas, public GIL-release counters, and heartbeat pauses are currently
truthful. Native adapter diagnostics include Canvas/Synth crate versions,
source/build digests, profile, and features. A benchmark snapshot digest mismatch
rejects the extension as stale; an unrecorded development build is marked
non-comparable rather than release-qualified.

Streaming and device schemas reserve first-audio/prefill time, queue high/low
watermarks, underruns, deadline ratio, stop latency, and cleanup completion.
Those fields remain unavailable for the SDL route until the native runtime
exposes them. Stateful memory/file cases report exact bytes, frames, public GIL
release render/write counters, and sink parity; block count, active voice/bus
high water, scratch/current/peak bytes, processor-state bytes, tail frames, and
limiter/normaliser latency remain unavailable at Python scope. The primary
metric remains measured elapsed work for the declared phase. A counter (for
example heartbeat observations) is a correctness diagnostic and must not be
substituted for elapsed time.

## Known defects and non-baseline behavior

The following are defects or incomplete migrations, not accepted output:

- process-history-dependent noise identity;
- unknown primitive/FX/filter/value coercion or silent substitution;
- sample or FX controls ignored after event creation;
- control, tail, limiter, or normaliser differences across arbitrary block boundaries (the canonical default-block sinks are exact, but configurable partition evidence is not exposed);
- Python value stringification or colliding mapping-key coercion;
- implicit packaged-sample lookup and undefined BPM-sensitive timeline behavior;
- unbounded durations, rates, controls, nesting, compressed plans, output, or
  cache allocation;
- a missing device selecting another playback route.

A case exercising an unresolved defect may be catalogued as unavailable with an
explicit reason, but it must not publish a successful baseline or silently run a
different workload.

## FX, output, failure, and longevity scope

All 34 practical Rust FX names remain executable with signal summaries. The new
chain/bus matrix adds depths 1/2/4/8 and independent bus counts 1/4/16/32, for 68
actual processor instances. Shared-versus-unique buses, limiter ceiling,
running-peak normaliser behavior, exact bytes/file output, and temporary-file
cleanup remain checked. The separately versioned causal lookahead normaliser is
implemented in Rust but is not selected or configured by the public render
route, so PBI 007's causal-normaliser matrix remains incomplete.

The fail-closed case now performs 21 bounded expected failures, adding infinite
and huge duration, zero sample rate, unknown stateful option, and malformed WAV
decode to the existing malformed container, non-finite, unknown synth/FX/chain,
missing asset, invalid control, unsupported value/key, and compressed-size
checks. It never opens a device or chooses another parser, decoder, synth, sample,
or player.

The longevity case runs exactly 120 compile/render cycles. Six evenly spaced
cycles use independent uncached stateful file sinks; the remainder use stateful
memory sinks. It requires one plan digest, one PCM digest, deleted files, public
render/write diagnostics, total materialized bytes, and a labelled net CPython
allocation-block delta. This is a bounded functional longevity run, not a
10–30-minute soak. Current/peak Rust cache/scratch/queue/handle/thread counts and
current RSS are not public and remain unavailable.

Comparable timing history is created only by a maintainer using a release build,
fixed workloads, retained raw samples, deterministic oracles, and exact route
 diagnostics. History is local and ignored, keyed by fingerprint and commit, and a
regression greater than 5% fails the local comparison. No macOS/Linux/Windows matrix,
A/A campaign, physical-device evidence, or cross-platform record is a completion gate.
Optional native-audio runs may remain unavailable.

## Focused commands

```sh
uv run pytest tests/unit/benchmark_system/test_synth_adapters.py -q
uv run pytest tests/unit/benchmark_system/test_synth_fixtures_oracles.py -q
uv run pytest tests/unit/benchmark_system/test_synth_catalog.py -q
uv run pytest tests/unit/benchmark_system/test_synth_dispatch.py -q
uv run pytest tests/unit/benchmark_system/test_synth_coverage.py -q
uv run python -m benchmarks.cli smoke benchmarks/synth_v1.toml
cargo test --manifest-path crates/gummy_synth/Cargo.toml
```

Run performance timing manually with the declared release provenance, fixed workload,
raw-sample, correctness, capability, and path-diagnostic checks. Do not invoke an
unavailable optional device workload as an offline fallback.
