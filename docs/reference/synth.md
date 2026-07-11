# Synth tracks

`gummysnake.synth` (`sy` in examples) provides a Pythonic logical-plan API for code-defined music. It is inspired by Sonic Pi, but it follows Gummy Snake conventions: snake_case names, deterministic plans, and native Python values at the public boundary. Python builds and serializes the logical/physical plan; audio rendering is delegated to the required Rust `gummysnake.rust._canvas` runtime, which registers synth bridge functions backed by `crates/gummy_synth`.

```python
from gummysnake import synth as sy

@sy.track(loop=True, seed=42)
def bassline():
    with sy.synth("tb303"), sy.fx("reverb", mix=0.25):
        note = sy.choose(sy.chord("e2", "minor"))
        sy.play(note, release=0.25, cutoff=sy.rrand(70, 120))
        sy.sleep(0.25)

track = bassline()
track.save("bassline.wav", duration=sy.duration(secs=8))
sound = track.to_sound("bassline.wav", duration=sy.duration(secs=8))
```

## Runtime organization

The public `gummysnake.synth` and `gummysnake.synth.core` modules are stable compatibility facades. Internally, `synth_runtime` has one-way, documented areas so contributors can follow a track from source composition to Rust-owned audio execution:

- `composition/` records decorators, contexts, event APIs, logical nodes, and plan builders.
- `values/` owns deterministic lazy expressions, rings, music helpers, and immutable synth/FX specifications.
- `physical/` expands logical plans, serializes `.gss`/`.gsfx` payloads, and invokes the required canvas-linked Rust synth bridge.
- `playback_export/` owns `Track` playback, WAV/MP3 and plan export, sample duration metadata, and in-memory `Sound` conversion.

The former flat `synth_runtime` module paths have been removed. Internal imports must use the owning area above; `gummysnake.synth` remains the supported public API. `playback_export` is deliberately not named `playback` so its ownership is explicit and it cannot collide with a flat runtime module.

## Track lifecycle

- `@sy.track` decorates a function that records logical actions.
- `@sy.track(loop=True)` repeats the full plan until the render duration is filled.
- `@sy.track(loop_times=n)` repeats the full plan a fixed number of times.
- Calling a track outside another track returns a `Track` instance.
- Calling a decorated track from inside another track inlines its logical actions, which supports reusable riffs and drum patterns.

`Track` methods:

- `track.explain()` returns a logical-plan summary.
- `track.physical_plan(duration=...)` expands loops, random expressions, and controls into scheduled events.
- `track.render(duration=...)` sends the physical plan to Rust and returns stereo 16-bit PCM WAV bytes.
- `track.save(path, duration=..., format=sy.Format.WAV)` writes a WAV file.
- `track.save("name.gss", duration=...)` writes a binary serialized synth physical plan instead of audio.
- `track.save("name.gsfx", duration=...)` writes a binary serialized FX physical plan.
- `track.save(path, format=sy.Format.MP3, duration=...)` writes MP3 through `ffmpeg` when available.
- `track.to_sound(path, duration=...)` performs a full Rust-backed offline render and returns a `gs.Sound` backed by in-memory WAV bytes.
- `track.play(duration=...)` serializes the bounded physical plan and hands it directly to the Rust audio bridge, which renders/mixes and queues playback on the native audio device without Python event scheduling, temporary WAV files, or platform-player subprocesses. Exact cached renders from `track.render(...)` or `track.save(...wav...)` are queued as in-memory WAV bytes without rendering again. It returns a `TrackPlayback` handle with `stop()`, `wait_until_stop()`, `join()`, and `is_playing()`.
- `track.play(duration=..., realtime=False)` keeps the offline behavior: render the full track to a `Sound`, start it, and return that `Sound`.

## Logical actions

- `sy.play(note, **opts)` triggers the current synth.
- `sy.sample(name_or_path, **opts)` triggers a bundled Sonic Pi sample by name, or an external PCM WAV/FLAC path.
- `sy.sleep(beats)` advances the logical timeline.
- `sy.control(handle, **opts)` changes a running synth/sample/FX handle.
- `event.when(condition)` conditionally keeps an event in the physical plan.

## Context managers

- `with sy.synth("dsaw", **defaults):` sets the synth for nested `play()` calls.
- `with sy.fx("reverb", **opts):` applies an FX chain to nested sound triggers.
- `with sy.fx("reverb") as reverb:` captures an FX handle that can be controlled.
- `with sy.loop(times=8):` repeats a block a fixed number of times.
- `with sy.loop():` records an open-ended loop that renders until the requested duration.
- `with sy.thread():` starts a nested block in parallel with surrounding code.

## Music and random helpers

The synth module includes deterministic lazy helpers that are evaluated when a physical plan is built:

- `sy.choose(values)`, `sy.rand()`, `sy.rand_i(max)`, `sy.rrand(low, high)`, `sy.rrand_i(low, high)`, `sy.dice(sides)`, and `sy.one_in(sides)`.
- `sy.note("c4")`, `sy.chord("e3", "minor")`, `sy.scale("e3", "minor_pentatonic", num_octaves=2)`, and `sy.octs("e1", 3)`.
- `sy.ring(...)`, `sy.range(...)`, `sy.line(...)`, `sy.bools(...)`, `sy.knit(...)`, and `sy.spread(...)`.
- `ring.tick(name=None)`, `ring.look(name=None)`, `sy.tick(name=None)`, and `sy.look(name=None)` for logical counters.

## Source-defined synths

Use `@sy.synth` to define reusable synths in Gummy Snake source. A source-defined synth receives the requested note/value plus option overrides, records ordinary synth actions, and can be used by name from `with sy.synth("name"):` contexts.

For new synth definitions, prefer the signal-builder style. It mirrors `@sy.track` plan construction while keeping the emitted runtime work as generic primitive events; multi-layer oscillator banks compile to one `_layered` primitive so slides, envelopes, filters, FX, and realtime scheduling are shared across the layers:

```python
@sy.synth(name="soft_saw")
def soft_saw(note=60, **opts):
    signal = (
        sy.synth_input(note, defaults={"release": 0.25, "cutoff": 90}, **opts)
        .layer("saw", amp=0.7)
        .layer("sine", transpose=12, amp=0.15)
    )
    signal.output()

@sy.track
def phrase():
    with sy.synth("soft_saw"):
        sy.play("e3", release=0.25)
```

`sy.synth_input(note, defaults={...}, **opts)` starts an immutable `SynthSignal`. Use `.layer(wave, transpose=..., amp=..., **opts)` for primitive oscillator layers, `.sample(name_or_path, **opts)` for sample-player definitions, `.silence(**opts)` for offline-silent utility definitions, and `.output()` (or `sy.synth_output(signal)`) to record the signal into the active synth plan. A single layer emits its direct primitive (`_saw`, `_sine`, etc.); multiple oscillator layers emit one `_layered` primitive carrying serializable layer metadata. Low-level primitive synth names are intentionally prefixed with `_` so they do not collide with source-defined Sonic Pi-style built-ins.

## Physical-plan assets

A `.gss` or `.gsfx` file is a versioned binary Gummy Snake Synth container for an expanded `PhysicalPlan`. `.gss` is used for synth/track plans and `.gsfx` is used for compiled FX plans. Both store concrete scheduled events/controls, not lazy expressions, so they can be loaded without executing the source track:

```python
track.save("lead.gss", duration=sy.duration(secs=2))
plan = sy.load_physical_plan("lead.gss")
wav_bytes = plan.render()
```

Bundled Sonic Pi-style synth source definitions live as one `@sy.synth` module per synth in `assets/synths/src/`. They use the `SynthSignal` builder to compose low-level primitive or `_layered` synth events and are compiled to `assets/synths/compiled/*.gss`.

Bundled Sonic Pi-style FX source definitions live as one `@sy.fx` module per FX in `assets/fx/src/`. They use `sy.fx_input()`/`sy.fx_output()` with `FxSignal` methods to compose generic low-level FX operations and are compiled to `assets/fx/compiled/*.gsfx`.

Compile both asset sets with:

```sh
uv run python scripts/compile_synth_assets.py
```

Compiled built-ins are exposed as assets:

```python
names = sy.builtin_synth_names()
plan = sy.load_builtin_synth_plan("tb303")
fx_names = sy.builtin_fx_names()
fx_plan = sy.load_builtin_fx_plan("reverb")
```

## Synths

`sy.synth(name, **opts)` accepts the documented Sonic Pi synth keys below. These built-ins are source-defined Gummy Snake synth plans, not per-key Rust dispatch branches. During planning they expand into primitive events such as `_sine`, `_saw`, `_fm`, `_noise`, and the generic oscillator-bank primitive `_layered`, which the Rust renderer turns into stable, audible Gummy Snake-native approximations. They are not bit-identical SuperCollider/Sonic Pi implementations.

Supported synth keys are generated from the non-FX `SynthDef` names in Sonic Pi's `etc/synthdefs/designs/` tree, plus public aliases retained from the Sonic Pi synth cheatsheet:

- `dark_ambience`
- `hollow`
- `growl`
- `beep`
- `pulse`
- `subpulse`
- `square`
- `saw`
- `tri`
- `dsaw`
- `dtri`
- `dpulse`
- `fm`
- `mod_fm`
- `mod_saw`
- `mod_dsaw`
- `mod_sine`
- `mod_tri`
- `mod_pulse`
- `dull_bell`
- `pretty_bell`
- `chiplead`
- `chipbass`
- `chipnoise`
- `babbling`
- `woah`
- `arpeg-click`
- `space_organ`
- `saws`
- `stereo_warp_sample`
- `dark_ambience_gated`
- `hollow_gated`
- `growl_gated`
- `beep_gated`
- `pulse_gated`
- `subpulse_gated`
- `square_gated`
- `saw_gated`
- `tri_gated`
- `dsaw_gated`
- `dtri_gated`
- `dpulse_gated`
- `fm_gated`
- `mod_fm_gated`
- `mod_saw_gated`
- `mod_dsaw_gated`
- `mod_sine_gated`
- `mod_tri_gated`
- `mod_pulse_gated`
- `chiplead_gated`
- `chipbass_gated`
- `chipnoise_gated`
- `bnoise_gated`
- `pnoise_gated`
- `gnoise_gated`
- `noise_gated`
- `cnoise_gated`
- `tb303_gated`
- `hoover_gated`
- `supersaw_gated`
- `zawa_gated`
- `prophet_gated`
- `tech_saws_gated`
- `pluck_gated`
- `blade_gated`
- `singer`
- `dark_sea_horn`
- `amp_stereo_monitor`
- `bnoise`
- `pnoise`
- `gnoise`
- `noise`
- `cnoise`
- `tb303`
- `hoover`
- `supersaw`
- `zawa`
- `prophet`
- `basic_mono_player`
- `basic_stereo_player`
- `mono_player`
- `stereo_player`
- `stereo_player-future`
- `mono_player-future`
- `mixer`
- `basic_mixer`
- `recorder`
- `live_audio_mono`
- `live_audio_stereo`
- `sound_in`
- `sound_in_stereo`
- `scope`
- `server-info`
- `tech_saws`
- `pluck`
- `blade`
- `bass_foundation`
- `bass_highend`
- `gabberkick`
- `bass_foundation_gated`
- `bass_highend_gated`
- `gabberkick_gated`
- `kalimba_gated`
- `piano_gated`
- `rhodey_gated`
- `rodeo_gated`
- `winwood_lead_gated`
- `kalimba`
- `organ_tonewheel`
- `piano`
- `rhodey`
- `rodeo`
- `sc808_bassdrum`
- `sc808_snare`
- `sc808_clap`
- `sc808_tomlo`
- `sc808_tommid`
- `sc808_tomhi`
- `sc808_congalo`
- `sc808_congamid`
- `sc808_congahi`
- `sc808_rimshot`
- `sc808_claves`
- `sc808_maracas`
- `sc808_cowbell`
- `sc808_closed_hihat`
- `sc808_open_hihat`
- `sc808_cymbal`
- `winwood_lead`
- `sine`
- `mod_beep`
- `main_mixer`

Sample-player synth definitions include `mono_player`, `stereo_player`, `basic_mono_player`, `basic_stereo_player`, and the future/warp player designs. Live-input, mixer, recorder, scope, monitor, and server-info utility definitions are represented as compiled plans but render silence in offline Gummy Snake tracks because live audio routing/input is not implemented.

## FX

`sy.fx(name, **opts)` accepts the documented Sonic Pi FX keys below. Like `@sy.synth`, `@sy.fx(name="...")` can define reusable source FX. Built-in public FX are source-defined and expand to generic low-level `_chain` FX operations; Rust `gummy_synth` executes those operations and the shared Sonic Pi-style FX wrapper (`pre_amp`, `pre_mix`, `mix`, and `amp`). The DSP implementations are Gummy Snake-native approximations designed to honor the public key/option surface and produce stable, audible effects; they are not bit-identical SuperCollider/Sonic Pi implementations.

Supported FX keys:

- `bitcrusher`
- `krush`
- `reverb`
- `gverb`
- `level`
- `echo`
- `slicer`
- `panslicer` (also accepts `pan_slicer`)
- `wobble`
- `ixi_techno`
- `compressor`
- `whammy`
- `rlpf`
- `nrlpf`
- `rhpf`
- `nrhpf`
- `hpf`
- `nhpf`
- `lpf`
- `nlpf`
- `normaliser` (also accepts `normalizer`)
- `distortion`
- `pan`
- `bpf`
- `nbpf`
- `rbpf`
- `nrbpf`
- `band_eq`
- `tanh`
- `pitch_shift`
- `ring_mod`
- `octaver`
- `vowel`
- `flanger`

Common Sonic Pi options such as `amp`, `mix`, `pre_amp`, and `pre_mix` are handled by the FX wrapper where documented. Effect-specific options such as filter cutoffs, resonance, panning, modulation phase/waveform, pitch, band EQ gain, vowel/voice selection, flanger depth/feedback, and reverb/echo timing are forwarded to the generic native FX operations.

## Current scope

This synth runtime supports deterministic logical planning, `@sy.synth` source-defined synths, `@sy.fx` source-defined FX, binary `.gss`/`.gsfx` physical-plan serialization, Rust-backed WAV rendering from serialized physical plans, primitive synth/sample/FX event execution in Rust, bounded playback via a Rust-rendered full-track buffer, bundled Sonic Pi CC0 samples, external PCM WAV/FLAC samples, common synth waveforms, ADSR-style envelopes, panning, basic controls/slides, compiled bundled synth/FX plan assets, and the Sonic Pi-inspired synth/FX surfaces listed above. A missing or stale `gummysnake.rust._canvas` runtime raises a Gummy Snake capability error with rebuild guidance.

The bundled sample library lives at `assets/samples/sonic_pi/` in the source tree and includes Sonic Pi's `README.md` with CC0 attribution/source notes. Sample names are resolved without the file extension, for example `sy.sample("bd_haus")` resolves to `bd_haus.flac`. Bundled compiled synth assets live at `assets/synths/compiled/`; bundled compiled FX assets live at `assets/fx/compiled/`.

Per the project rules and initial feature request, this API intentionally does not implement live loops, MIDI in/out, OSC, live audio input, multichannel sound output routing, or Minecraft APIs. The module leaves room for those to become runtime-backed extensions later.
