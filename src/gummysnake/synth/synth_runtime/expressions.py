"""Compatibility shim for lazy expression nodes.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.values.expressions`.
"""

import sys

from gummysnake.synth.synth_runtime.values import expressions as _implementation

sys.modules[__name__] = _implementation
