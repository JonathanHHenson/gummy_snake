"""Private Rust-bridge adapters behind :class:`gummysnake.ecs.world_facade.EcsWorld`.

The modules are grouped by the boundary they adapt, not by public API names:

- ``entities`` and ``query`` validate entity handles and materialize friendly
  views over Rust-owned entity/query results;
- ``resources`` adapts Rust resources and event queues;
- ``python_batch`` and ``python_system`` are the explicit Python UDF/system
  boundary, including only frame-local view caching and buffered Rust writes;
- ``physical`` and ``physical_execution/`` serialize, compile, execute, and
  report Rust physical plans;
- ``state`` maintains facade diagnostics, change markers, and cache invalidation.

Dependency direction is one way: public facade and runtime views call these
adapters; adapters call the Rust bridge. Physical execution never calls the
Python UDF adapter, and Python UDF adapters never become a fallback for
non-UDF plans. The scheduler composes those boundaries separately.
"""
