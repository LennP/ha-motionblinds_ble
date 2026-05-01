"""Conftest for the motionblinds_ble integration tests.

Run with:
    /tmp/hatest/bin/python -m pytest tests/ -v

Layout:
    The tests rely on `pytest-homeassistant-custom-component`. That plugin
    looks for `custom_components/<domain>` *inside its own testing_config
    directory*, so the integration must be symlinked there before the
    tests run. The CI step (or local setup) is documented in the README;
    here we just enable the helper fixture.
"""

import sys
from pathlib import Path

import pytest

# Make `custom_components.motionblinds_ble` importable for direct module access
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable the custom integrations defined in the test directory."""
    yield
