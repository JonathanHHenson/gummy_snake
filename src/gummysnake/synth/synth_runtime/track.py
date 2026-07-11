"""Compatibility shim for the public Track implementation.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.playback_export.track`.
"""

import sys

from gummysnake.synth.synth_runtime.playback_export import track as _implementation

sys.modules[__name__] = _implementation
