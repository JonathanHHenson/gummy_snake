# Synth causal normaliser migration

Epic 320 replaces the legacy whole-buffer peak normalisation path with one
versioned, stateful processor. This document is the contract for that migration;
it does **not** claim that the legacy full-track renderer already has these
semantics.

## Contract v1

`gummy_synth::CausalNormaliser` is the canonical processor primitive for the
future block renderer. Version 1 has these fixed semantics:

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

The current legacy helpers `normalise_pair()` and `fx_normaliser()` scan an
entire supplied signal and apply one global gain. They are a documented
non-authoritative baseline for signal comparison only; they must not be used as
the expected output for the v1 processor.

The causal processor is intentionally not wired into only one legacy route. The
cutover happens when the Epic 320 stateful block renderer owns every offline,
finite, open, file, bytes, rendered-sound, and SDL sink. That cutover is
responsible for:

1. compiling normaliser options into typed processor configuration;
2. preserving the processor state across blocks, silence, and effect tails;
3. applying FX-bus controls at exact frame boundaries;
4. removing whole-signal normalisation from all execution routes; and
5. versioning public signal/oracle expectations as an explicit semantic
   migration.

Until then, contributors must not describe current `Track.render()`,
`Track.save()`, finite playback, or public `Sound` playback as causal-normaliser
routes.

## Validation requirements for cutover

A route may adopt v1 only after it passes:

- exact partition/flush equivalence for direct processor input;
- signal checks covering startup, sustained input, transients, silence, and
  recovery;
- channel-link and sample-rate checks;
- shared FX-bus controls during input, silence, and tails; and
- offline, finite SDL, and open stream parity using the one block engine.

Device hardware qualification remains a separate operational gate. No headless
or simulated result may be reported as physical-audio qualification.
