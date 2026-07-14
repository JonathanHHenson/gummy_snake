# Synth causal normaliser migration

Epic 320 replaces whole-buffer peak normalisation with one versioned, stateful
processor. The stateful block renderer and its offline, rendered-Sound, finite
SDL, and rolling SDL sinks now use this contract for the public normaliser FX.

## Contract v1

`gummy_synth::CausalNormaliser` is the canonical processor primitive for the
block renderer. Version 1 has these fixed semantics:

- Stereo channels are linked: each gain decision uses the greatest absolute
  sample across both channels.
- The processor observes at most a fixed **5 ms** lookahead window at the active
  sample rate. It never scans the complete program or future blocks.
- The selected gain approaches a target of `1.0` using a **1 ms attack** when
  reducing gain and a **50 ms release** when recovering gain. Durations are
  converted with the shared checked frame-count policy.
- Input is delayed by the exact lookahead frame count. Finite sinks must flush
  once to emit those delayed frames; open streams retain the delay until close.
- Silence uses a target gain of `1.0`, allowing the gain envelope to recover
  through silence and tails. The processor does not manufacture audio for
  silent frames.
- Processing is deterministic and exactly invariant under arbitrary input block
  partitioning, provided the same finite flush policy is used.
- A finite block and its flush have the same frame count as their input. The
  normaliser has no independent audio tail beyond its fixed latency.

The contract is exported as
`CAUSAL_NORMALISER_CONTRACT_VERSION = 1`. Its Rust tests cover fixed latency,
channel linking, bounded lookahead, finite flush, configuration validation, and
exact partition equivalence.

## Migration boundary

The old `normalise_pair()`/`fx_normaliser()` helpers remain only behind
superseded whole-event compatibility rendering and are non-authoritative. They
must not be used as expected output for the v1 processor or selected by canonical
track/Sound/device routes.

The stateful block renderer owns offline, finite, open, file, bytes,
rendered-sound, and SDL sinks. The remaining migration work is responsible for:

1. compiling normaliser options into typed processor configuration;
2. preserving the processor state across blocks, silence, and effect tails;
3. applying FX-bus controls at exact frame boundaries;
4. deleting whole-signal normalisation with the remaining whole-event helpers; and
5. versioning public signal/oracle expectations as an explicit semantic
   migration.

`Track.render()`, `Track.save()`, `Track.to_sound()`, finite/rolling playback,
and public rendered `Sound` playback all consume canonical block-engine PCM. A
raw loaded `Sound` asset does not apply synth FX; it only uses the shared native
mixer and canonical dynamic resampler.

## Validation requirements for cutover

A route may adopt v1 only after it passes:

- exact partition/flush equivalence for direct processor input;
- signal checks covering startup, sustained input, transients, silence, and
  recovery;
- channel-link and sample-rate checks;
- shared FX-bus controls during input, silence, and tails; and
- offline, finite SDL, and open stream parity using the one block engine.

Native-audio runs are optional manual information. They report the route actually
executed and never relabel headless or simulated output as native-audio output.
