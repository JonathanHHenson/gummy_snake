"""Compatibility shim for logical event APIs.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.composition.event_api`.
"""

import sys

from gummysnake.synth.synth_runtime.composition import event_api as _implementation

sys.modules[__name__] = _implementation
