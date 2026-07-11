"""Compatibility shim for logical-plan builder internals.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.composition.plan_builder`.
"""

import sys

from gummysnake.synth.synth_runtime.composition import plan_builder as _implementation

sys.modules[__name__] = _implementation
