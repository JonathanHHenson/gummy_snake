"""Legacy executable forwarding adapter for the canvas benchmark child."""

from __future__ import annotations

from canvas_backend_perf.child import _flatten_metrics, main

__all__ = ["_flatten_metrics", "main"]

if __name__ == "__main__":
    main()
