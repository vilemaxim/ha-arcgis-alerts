"""Fixtures for ArcGIS Alerts tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.arcgis_alerts.const import PRESETS

FIXTURES = Path(__file__).parent / "fixtures"

LAYER_URL = PRESETS["swbno_boil_water"]["layer_url"]
QUERY_URL = f"{LAYER_URL}/query"

# A public point in the French Quarter, covered by three historical SWBNO
# advisory polygons when the fixtures were recorded (2026-10-06).
TEST_LATITUDE = 29.9574
TEST_LONGITUDE = -90.0629


def load_fixture(name: str) -> dict[str, Any]:
    """Load a recorded ArcGIS response."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in every test."""
    return


@pytest.fixture(autouse=True)
def test_home(hass):
    """Put Home Assistant's home location on the public test point."""
    hass.config.latitude = TEST_LATITUDE
    hass.config.longitude = TEST_LONGITUDE
