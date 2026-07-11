"""Compatibility shim for lazy values and rings.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.values.lazy_values`.
"""

import sys

from gummysnake.synth.synth_runtime.values import lazy_values as _implementation

sys.modules[__name__] = _implementation
