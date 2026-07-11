"""Compatibility shim for musical and random helper functions.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.values.pattern_helpers`.
"""

import sys

from gummysnake.synth.synth_runtime.values import pattern_helpers as _implementation

sys.modules[__name__] = _implementation
