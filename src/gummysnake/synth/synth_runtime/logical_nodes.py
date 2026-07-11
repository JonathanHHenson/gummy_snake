"""Compatibility shim for logical-plan node types.

Canonical implementation: :mod:`gummysnake.synth.synth_runtime.composition.logical_nodes`.
"""

import sys

from gummysnake.synth.synth_runtime.composition import logical_nodes as _implementation

sys.modules[__name__] = _implementation
