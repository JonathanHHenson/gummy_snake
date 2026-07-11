"""Legacy executable forwarding adapter for ECS performance scenarios."""

from __future__ import annotations

from ecs_scenarios_perf_child import main

__all__ = ["main"]

if __name__ == "__main__":
    main(__import__("sys").argv)
