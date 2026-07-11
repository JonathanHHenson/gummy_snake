"""Compatibility shim for the track decorator.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.composition.track_decorator`.
"""

import sys

from gummysnake.synth.synth_runtime.composition import track_decorator as _implementation

sys.modules[__name__] = _implementation
