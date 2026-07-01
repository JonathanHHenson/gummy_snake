# Gummy Snake Documentation

This documentation is split by audience:

- [Getting started](getting_started/index.md): learn Gummy Snake by writing sketches.
- [Reference](reference/index.md): look up public APIs by topic.
- [Contributor docs](contribute/index.md): understand the codebase, runtime, and
  project workflow.

Gummy Snake examples and reference docs favor Python-first APIs: decorator callbacks,
property-style sketch/input state, context managers for temporary drawing state,
async-compatible asset loading, Python data-model helpers for vectors, events,
and images, and dataclass-based ECS components/resources whose systems execute
through the Rust physical ECS runtime.

Start with [Entity component systems](reference/ecs.md) when building
simulation-heavy sketches or games. Maintainers changing ECS internals should
read [ECS architecture](contribute/ecs_architecture.md) and
[ECS debugging and performance triage](contribute/ecs_debugging.md).
