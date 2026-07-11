"""Compatibility shim for sample metadata and export helpers.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.playback_export.samples_and_export`.
"""

import sys

from gummysnake.synth.synth_runtime.playback_export import samples_and_export as _implementation

sys.modules[__name__] = _implementation
