"""Compatibility shim for physical-plan serialization helpers.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.physical.serialization`.
"""

import sys

from gummysnake.synth.synth_runtime.physical import serialization as _implementation

sys.modules[__name__] = _implementation
