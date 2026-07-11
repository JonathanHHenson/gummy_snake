"""Compatibility shim for music scales and synth/FX specifications.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.values.scales_and_specs`.
"""

import sys

from gummysnake.synth.synth_runtime.values import scales_and_specs as _implementation

sys.modules[__name__] = _implementation
