"""Compatibility shim for decorated synth, FX, and track definitions.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.composition.definitions`.
"""

import sys

from gummysnake.synth.synth_runtime.composition import definitions as _implementation

sys.modules[__name__] = _implementation
