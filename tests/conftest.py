"""Fixtures for the EnergyCalc tests."""

from __future__ import annotations

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request: pytest.FixtureRequest):
    """Make Home Assistant load the custom component under test.

    ``recorder_mock`` has to be resolved before the ``hass`` fixture is set up,
    so pull it in first when a test asks for it.
    """
    if "recorder_mock" in request.fixturenames:
        request.getfixturevalue("recorder_mock")
    request.getfixturevalue("enable_custom_integrations")
