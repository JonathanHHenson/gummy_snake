"""Internal implementation areas for :mod:`gummysnake.synth.core`.

The runtime is organized by phase:

* :mod:`.composition` records logical track and source-definition plans.
* :mod:`.values` evaluates deterministic lazy values and owns signal specs.
* :mod:`.physical` expands and serializes plans before using the Rust bridge.
* :mod:`.playback_export` owns bounded playback, export, and Sound conversion.

The direct modules in this package are explicit compatibility shims for supported
legacy imports. They deliberately do not share a stem with any implementation
package, so imports cannot be shadowed by a module/package collision.
"""
