"""Retired synth-track monolith.

Focused synth-track tests live in ``test_synth_tracks_*`` modules.
"""

import pytest


@pytest.mark.skip(
    reason="Retired monolith; focused synth-track tests live in test_synth_tracks_* modules."
)
def test_synth_tracks_monolith_retired() -> None:
    """Keep the retired monolith path diagnostic-clean without duplicating tests."""
