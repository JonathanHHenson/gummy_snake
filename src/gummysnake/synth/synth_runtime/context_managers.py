"""Compatibility shim for composition context-manager internals.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.composition.context_managers`.
"""

import sys

from gummysnake.synth.synth_runtime.composition import context_managers as _implementation

sys.modules[__name__] = _implementation
