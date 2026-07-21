"""Weaviate smoke test — OPT-IN only (deferred vector backend).

Skipped unless CLE_RUN_INTEGRATION=1: no default test depends on
Weaviate, CI never runs this.
"""

import os

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skipif(os.getenv("CLE_RUN_INTEGRATION") != "1",
                    reason="integration tests are opt-in (CLE_RUN_INTEGRATION=1)")
def test_weaviate_backend_smoke() -> None:
    weaviate = pytest.importorskip("weaviate")
    assert hasattr(weaviate, "connect_to_local")  # client v4 surface
