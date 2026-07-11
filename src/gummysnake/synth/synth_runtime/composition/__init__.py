"""Logical synth composition and plan-construction internals.

This area owns builder state, decorators, contexts, event APIs, and logical nodes.
It depends only on the ``values`` area plus physical-plan types at serialization
boundaries; it does not render or play audio.
"""
