"""Compatibility shim for physical-plan types.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.physical.physical_plan`.
"""

import sys

from gummysnake.synth.synth_runtime.physical import physical_plan as _implementation

sys.modules[__name__] = _implementation
