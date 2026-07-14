"""Internal ownership boundary for Python-declared ECS logical plans.

The hierarchy separates plan construction from world/runtime execution:

- :mod:`actions` defines action nodes, structural commands, and UDF declarations.
- :mod:`expressions` defines lazy expression nodes, proxies, aggregates, and helpers.
- :mod:`building` owns context-local plan-build sessions and scopes.
- :mod:`inspection` owns plan analysis and human-readable explain output.
- :mod:`systems` owns decorators and built-plan definitions.
- :mod:`specifications` owns annotation specifications and event proxies.

Public imports remain available through :mod:`gummysnake.ecs`. This package must
not import world-runtime or renderer implementations; Rust remains the non-UDF
ECS execution boundary.
"""

from __future__ import annotations
