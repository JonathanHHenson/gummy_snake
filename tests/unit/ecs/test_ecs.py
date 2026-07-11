"""Retired ECS monolith.

Focused ECS tests live in ``test_ecs_*`` modules.
"""

import pytest


@pytest.mark.skip(reason="Retired monolith; focused ECS tests live in test_ecs_* modules.")
def test_ecs_monolith_retired() -> None:
    """Keep the retired monolith path diagnostic-clean without duplicating tests."""
