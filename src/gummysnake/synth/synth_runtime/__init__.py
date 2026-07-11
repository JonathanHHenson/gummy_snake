"""Internal implementation areas for :mod:`gummysnake.synth.core`.

The runtime is organized by phase:

* :mod:`.composition` records logical track and source-definition plans.
* :mod:`.values` evaluates deterministic lazy values and owns signal specs.
* :mod:`.physical` expands and serializes plans before using the Rust bridge.
* :mod:`.playback_export` owns bounded playback, export, and Sound conversion.

The runtime has no flat implementation or compatibility modules. Import the
owning domain package directly when working on internals.
"""
